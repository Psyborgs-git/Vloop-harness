"""Approval_Manager — pause, resume, and reject Workflow_Run checkpoints.

The Approval_Manager is the Control_Plane subsystem that handles
Approval_Checkpoints: Workflow_Steps that require an explicit user decision
before execution continues. It cooperates with the :class:`~core.dag_executor.DagExecutor`,
which intercepts a ready step of type ``"approval"`` and hands it here instead
of dispatching it to a worker (see ``DagExecutor._schedule_ready``).

Lifecycle (Requirement 8):

* :meth:`enter_checkpoint` sets the step to ``awaiting-approval``, persists both
  the step and run state so a pending approval survives a Control_Plane restart
  (Requirement 8.5), and emits an ``approval-required`` event carrying the
  checkpoint context (Requirements 8.1, 8.2). Its dependents are paused
  structurally: they depend on the checkpoint step and therefore cannot be
  scheduled until it completes.
* :meth:`approve` records the (optionally edited) decision as the checkpoint
  step's output, marks the step ``completed``, and resumes the run from the
  checkpoint so its dependents become schedulable (Requirement 8.3).
* :meth:`reject` records the rejection on the checkpoint step, marks every
  transitive dependent ``skipped`` so none of them execute, and drives the run
  to the terminal ``rejected`` state (Requirement 8.4).
* :meth:`pending_for_run` lists the checkpoints currently awaiting a decision,
  reconstructed from persistence so it is restart-safe.

Persistence reuses the existing ``workflow_steps``/``workflow_runs`` tables and
the :class:`~core.event_router.EventRouter`. While a checkpoint is awaiting a
decision, its context is parked in the step's ``output_json`` column; on a
decision that column is overwritten with the decision outcome (which dependents
read as the checkpoint's output).
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from core.database import DatabaseBackend
from core.event_router import EventRouter, WorkflowEventType
from core.helpers import from_json, now_iso, to_json
from core.orchestration_types import RunState, StepState

LOGGER = logging.getLogger("vloop.control_plane.approval_manager")


class ApprovalManager:
    """Pause/resume/reject Approval_Checkpoints within a Workflow_Run."""

    def __init__(
        self,
        state: DatabaseBackend,
        events: EventRouter,
        executor: Any | None = None,
    ) -> None:
        self._state = state
        self._events = events
        # The DagExecutor is injected after construction (the executor also
        # accepts this manager as a collaborator, so the two are wired with a
        # mutual reference). :meth:`approve` needs it to resume the run.
        self._executor = executor
        self._lock = threading.RLock()

    def attach_executor(self, executor: Any) -> None:
        """Wire the DagExecutor used to resume a run after approval.

        Construction is mutual (the executor takes this manager as its
        ``approvals`` collaborator), so the executor reference is supplied here
        once both objects exist.
        """
        self._executor = executor

    # -- entering a checkpoint (Requirements 8.1, 8.2, 8.5) ----------------

    def enter_checkpoint(
        self, run_id: str, step_id: str, context: dict[str, Any]
    ) -> None:
        """Pause ``step_id`` for approval and announce it to the Frontend.

        Sets the step to ``awaiting-approval`` and the run to
        ``awaiting_approval`` (both persisted so the pending approval survives a
        restart, Requirement 8.5), parks the checkpoint ``context`` on the step,
        and emits an ``approval-required`` event carrying that context
        (Requirements 8.1, 8.2). The checkpoint's dependents are paused
        structurally — they depend on this step and cannot run until it
        completes.
        """
        with self._lock:
            step = self._load_step(run_id, step_id)
            if step is None:
                raise ValueError(
                    f"unknown step '{step_id}' for run '{run_id}'"
                )

            self._state.execute(
                "UPDATE workflow_steps SET state = ?, output_json = ? "
                "WHERE run_id = ? AND step_id = ?",
                (
                    StepState.AWAITING_APPROVAL.value,
                    to_json(context or {}),
                    run_id,
                    step_id,
                ),
            )
            self._state.execute(
                "UPDATE workflow_runs SET state = ? WHERE id = ?",
                (RunState.AWAITING_APPROVAL.value, run_id),
            )

            self._events.emit(
                run_id,
                WorkflowEventType.STEP_STATE_CHANGED,
                f"step {step_id} -> {StepState.AWAITING_APPROVAL.value}",
                step_id=step_id,
                payload={"state": StepState.AWAITING_APPROVAL.value},
            )
            self._events.emit(
                run_id,
                WorkflowEventType.APPROVAL_REQUIRED,
                f"step {step_id} requires approval",
                step_id=step_id,
                payload={"context": context or {}},
            )

    # -- resuming on approval (Requirement 8.3) ----------------------------

    def approve(
        self,
        run_id: str,
        step_id: str,
        edits: dict[str, Any] | None = None,
        *,
        block: bool = True,
        timeout: float | None = None,
    ) -> RunState:
        """Approve a checkpoint and resume execution from it.

        Records the decision (and any ``edits``) as the checkpoint step's
        output, marks the step ``completed``, and re-drives the run so its
        dependents become schedulable (Requirement 8.3). Returns the resulting
        run state. Raises ``ValueError`` if the step is not awaiting approval.
        """
        with self._lock:
            self._require_awaiting(run_id, step_id)
            output: dict[str, Any] = {"approved": True}
            if edits:
                output["edits"] = edits
            self._state.execute(
                "UPDATE workflow_steps SET state = ?, output_json = ?, "
                "finished_at = COALESCE(finished_at, ?) "
                "WHERE run_id = ? AND step_id = ?",
                (
                    StepState.COMPLETED.value,
                    to_json(output),
                    now_iso(),
                    run_id,
                    step_id,
                ),
            )
            self._events.emit(
                run_id,
                WorkflowEventType.STEP_STATE_CHANGED,
                f"step {step_id} -> {StepState.COMPLETED.value}",
                step_id=step_id,
                payload={"state": StepState.COMPLETED.value, "approved": True},
            )

        # Resume outside the manager lock so the executor's scheduling lock is
        # never acquired while this lock is held.
        if self._executor is None:
            raise RuntimeError(
                "no executor attached; cannot resume run after approval"
            )
        return self._executor.execute_run(run_id, block=block, timeout=timeout)

    # -- rejecting (Requirement 8.4) ---------------------------------------

    def reject(self, run_id: str, step_id: str, reason: str) -> RunState:
        """Reject a checkpoint, terminating the run as ``rejected``.

        Records the rejection on the checkpoint step, marks every transitive
        dependent ``skipped`` so none of them execute, and sets the run to the
        terminal ``rejected`` state (Requirement 8.4). Returns ``RunState.REJECTED``.
        Raises ``ValueError`` if the step is not awaiting approval.
        """
        with self._lock:
            self._require_awaiting(run_id, step_id)

            # The checkpoint itself is recorded as cancelled-by-decision.
            self._state.execute(
                "UPDATE workflow_steps SET state = ?, output_json = ?, "
                "error_message = ?, finished_at = COALESCE(finished_at, ?) "
                "WHERE run_id = ? AND step_id = ?",
                (
                    StepState.CANCELLED.value,
                    to_json({"approved": False, "reason": reason}),
                    reason,
                    now_iso(),
                    run_id,
                    step_id,
                ),
            )
            self._emit_step_state(run_id, step_id, StepState.CANCELLED)

            # Dependents must not execute (Requirement 8.4): skip every step
            # transitively downstream of the checkpoint that has not already
            # reached a terminal state.
            states = self._load_step_states(run_id)
            for dependent in sorted(self._transitive_dependents(run_id, step_id)):
                current = states.get(dependent)
                if current is not None and not current.is_terminal:
                    self._state.execute(
                        "UPDATE workflow_steps SET state = ?, "
                        "finished_at = COALESCE(finished_at, ?) "
                        "WHERE run_id = ? AND step_id = ?",
                        (StepState.SKIPPED.value, now_iso(), run_id, dependent),
                    )
                    self._emit_step_state(run_id, dependent, StepState.SKIPPED)

            self._state.execute(
                "UPDATE workflow_runs SET state = ?, "
                "finished_at = COALESCE(finished_at, ?) WHERE id = ?",
                (RunState.REJECTED.value, now_iso(), run_id),
            )
            self._events.emit(
                run_id,
                WorkflowEventType.RUN_REJECTED,
                "workflow run rejected",
                step_id=step_id,
                payload={"state": RunState.REJECTED.value, "reason": reason},
            )
        return RunState.REJECTED

    # -- listing pending approvals -----------------------------------------

    def pending_for_run(self, run_id: str) -> list[dict[str, Any]]:
        """List the checkpoints in ``run_id`` currently awaiting a decision.

        Reconstructed from persistence (the parked context lives in each
        awaiting-approval step's ``output_json``) so it is restart-safe.
        """
        rows = self._state.fetch_all(
            "SELECT step_id, output_json FROM workflow_steps "
            "WHERE run_id = ? AND state = ? ORDER BY step_id ASC",
            (run_id, StepState.AWAITING_APPROVAL.value),
        )
        return [
            {
                "run_id": run_id,
                "step_id": row["step_id"],
                "context": from_json(row["output_json"], {}) or {},
            }
            for row in rows
        ]

    # -- internals ----------------------------------------------------------

    def _require_awaiting(self, run_id: str, step_id: str) -> None:
        step = self._load_step(run_id, step_id)
        if step is None:
            raise ValueError(f"unknown step '{step_id}' for run '{run_id}'")
        if StepState(step["state"]) is not StepState.AWAITING_APPROVAL:
            raise ValueError(
                f"step '{step_id}' of run '{run_id}' is not awaiting approval "
                f"(state={step['state']})"
            )

    def _load_step(self, run_id: str, step_id: str) -> dict[str, Any] | None:
        return self._state.fetch_one(
            "SELECT * FROM workflow_steps WHERE run_id = ? AND step_id = ?",
            (run_id, step_id),
        )

    def _load_step_states(self, run_id: str) -> dict[str, StepState]:
        rows = self._state.fetch_all(
            "SELECT step_id, state FROM workflow_steps WHERE run_id = ?",
            (run_id,),
        )
        return {row["step_id"]: StepState(row["state"]) for row in rows}

    def _transitive_dependents(self, run_id: str, step_id: str) -> set[str]:
        """Return every step transitively downstream of ``step_id``.

        Built directly from the persisted ``depends_on`` edges so the manager
        does not depend on the executor for rejection.
        """
        rows = self._state.fetch_all(
            "SELECT step_id, depends_on_json FROM workflow_steps WHERE run_id = ?",
            (run_id,),
        )
        downstream: dict[str, set[str]] = {}
        for row in rows:
            sid = row["step_id"]
            for dep in from_json(row["depends_on_json"], []) or []:
                downstream.setdefault(dep, set()).add(sid)

        result: set[str] = set()
        stack = [step_id]
        while stack:
            current = stack.pop()
            for child in downstream.get(current, ()):  # type: ignore[arg-type]
                if child not in result:
                    result.add(child)
                    stack.append(child)
        return result

    def _emit_step_state(
        self, run_id: str, step_id: str, state: StepState
    ) -> None:
        self._events.emit(
            run_id,
            WorkflowEventType.STEP_STATE_CHANGED,
            f"step {step_id} -> {state.value}",
            step_id=step_id,
            payload={"state": state.value},
        )
