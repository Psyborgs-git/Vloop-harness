"""DAG_Executor — schedules, runs, and persists Workflow_Runs.

The DAG_Executor takes a validated Workflow_Definition (compiled into a
:class:`~core.dag.Dag`) and executes it: it creates a Workflow_Run, schedules
each step only once all of its dependencies have completed, runs ready steps up
to a configured concurrency limit, persists every step transition before the
next is scheduled, and finally derives the run outcome from the success-versus-
error of the relevant steps.

This module implements the *core scheduling* responsibilities (task 9.1):

* :meth:`DagExecutor.start_run` — create a Workflow_Run with a unique id and an
  initial state of ``pending``, persisting one ``workflow_steps`` row per step
  (Requirement 3.1, 3.7).
* :meth:`DagExecutor._schedule_ready` — schedule steps whose dependencies have
  all reached ``completed``, bounded by the run's concurrency limit
  (Requirements 3.2, 3.3, 3.4).
* :meth:`DagExecutor._on_step_complete` — persist a step's terminal transition
  and then schedule whatever became ready (Requirement 3.7).
* Run-outcome derivation — ``completed`` when every *relevant* step succeeded,
  ``failed`` when any relevant step ended in error; ``cancelled``/``skipped``
  steps never flip that determination (Requirements 3.5, 3.6).

Cancellation, retry, restart recovery (task 10), agent dispatch (task 11), and
approvals (task 12) build on this core and are intentionally out of scope here.

Dependency injection
---------------------
Every collaborating subsystem (agents, gateway, tools, approvals, hooks, infra)
is optional so this core can be constructed and tested in isolation. Step
execution itself is delegated to an injectable ``step_runner`` callable; the
agent-backed runner is wired in by task 11. When no runner is configured, a
step is marked ``failed`` with a descriptive message rather than crashing the
whole run.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

from core.dag import Dag, DagNode
from core.database import DatabaseBackend
from core.event_router import EventRouter, WorkflowEventType
from core.helpers import from_json, now_iso, to_json
from core.orchestration_types import RunState, StepResult, StepState
from core.workflow_serializer import WorkflowSerializer

LOGGER = logging.getLogger("vloop.control_plane.dag_executor")

# A step runner takes the run id, the step's DAG node, and a mapping of the
# completed upstream outputs (keyed by dependency step id) and returns the
# terminal StepResult for that step.
StepRunner = Callable[[str, DagNode, dict[str, Any]], StepResult]

# Step states that count toward the concurrency budget (occupy a slot).
_OCCUPYING_STATES: frozenset[StepState] = frozenset(
    {StepState.READY, StepState.RUNNING}
)

# Terminal statuses reported by the Agent_Orchestrator for an invocation.
_TERMINAL_INVOCATION_STATUSES: frozenset[str] = frozenset({"succeeded", "failed"})


class InvocationNotExecutedError(RuntimeError):
    """A configured agent invocation did not execute at all.

    Raised by an Agent_Orchestrator to signal that a dispatched invocation was
    never run (as opposed to running and failing). The DAG_Executor responds by
    stopping the whole Workflow_Run (Requirement 5.5).
    """


class InvocationEventRecordingError(RuntimeError):
    """Recording the invocation event for an agent invocation failed.

    Raised by an Agent_Orchestrator when it cannot durably record the
    invocation event. The DAG_Executor responds by stopping the whole
    Workflow_Run, since the run would otherwise proceed with an unauditable
    invocation (Requirement 5.6).
    """


class _StopRun(Exception):
    """Internal signal that an agent step requires the whole run to stop.

    Carries the human-readable reason recorded in the run event history. It is
    raised by the agent-backed step runner and caught by
    :meth:`DagExecutor._execute_step`, which aborts the run (Requirements 5.5,
    5.6).
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class _RunContext:
    """Per-run execution scratch state held while a run is being driven."""

    run_id: str
    dag: Dag
    concurrency_limit: int
    pool: ThreadPoolExecutor
    in_flight: set[str] = field(default_factory=set)
    # Maps an in-flight step id to the Kernel workload/job id backing it, so a
    # cancellation can tear the workload down (Requirement 4.2). Populated by
    # step runners via :meth:`DagExecutor.record_step_job`.
    jobs: dict[str, str] = field(default_factory=dict)
    finished: bool = False
    done: threading.Event = field(default_factory=threading.Event)


class DagExecutor:
    """Schedules and persists Workflow_Runs against a validated DAG."""

    def __init__(
        self,
        state: DatabaseBackend,
        agents: Any | None = None,
        gateway: Any | None = None,
        tools: Any | None = None,
        approvals: Any | None = None,
        hooks: Any | None = None,
        events: EventRouter | None = None,
        infra: Any | None = None,
        concurrency_limit: int = 1,
        *,
        serializer: WorkflowSerializer | None = None,
        step_runner: StepRunner | None = None,
        agent_poll_timeout: float = 300.0,
        agent_poll_interval: float = 0.05,
    ) -> None:
        self._state = state
        self._agents = agents
        self._gateway = gateway
        self._tools = tools
        self._approvals = approvals
        self._hooks = hooks
        self._events = events or EventRouter(state)
        self._infra = infra
        self._concurrency_limit = max(1, int(concurrency_limit))
        self._serializer = serializer or WorkflowSerializer()
        self._agent_poll_timeout = max(0.0, float(agent_poll_timeout))
        self._agent_poll_interval = max(0.0, float(agent_poll_interval))
        # Step execution is delegated to an injectable runner so the core can be
        # tested in isolation. When no runner is supplied but an Agent_Orchestrator
        # is wired in, dispatch agent steps through it by default (task 11) so no
        # orphaned dispatch path remains.
        if step_runner is None and agents is not None:
            self._step_runner: StepRunner | None = self._run_agent_step
        else:
            self._step_runner = step_runner

        # Serializes scheduling decisions and step-state transitions so that a
        # step completing on a worker thread cannot race the scheduler.
        self._lock = threading.RLock()
        self._contexts: dict[str, _RunContext] = {}

    # -- run creation (Requirement 3.1) ------------------------------------

    def start_run(
        self,
        definition_id: str,
        *,
        concurrency_limit: int | None = None,
    ) -> str:
        """Create a Workflow_Run for ``definition_id`` and return its id.

        The run is created with a unique identifier and an initial state of
        ``pending`` (Requirement 3.1); one ``workflow_steps`` row is persisted
        per step so the run's structure survives a restart (Requirement 3.7).
        Execution is *not* started here — call :meth:`execute_run` to drive the
        run to a terminal state.
        """
        definition = self._load_definition(definition_id)
        dag = self._dag_from_definition(definition)

        run_id = str(uuid.uuid4())
        limit = self._resolve_limit(definition, concurrency_limit)
        created_at = now_iso()

        self._state.execute(
            "INSERT INTO workflow_runs "
            "(id, definition_id, state, concurrency_limit, budget_json, "
            "created_at, started_at, finished_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                definition_id,
                RunState.PENDING.value,
                limit,
                None,
                created_at,
                None,
                None,
            ),
        )

        step_rows = [
            (
                run_id,
                node.step_id,
                node.step_type,
                StepState.PENDING.value,
                to_json(list(node.depends_on)),
                # Persist the step's static config (agent reference, configured
                # inputs, overrides) so it survives into execution and a restart
                # (Requirement 3.7); the rebuilt DAG restores it (see _load_dag).
                to_json(node.config),
                None,
                None,
                None,
                None,
            )
            for node in dag.nodes.values()
        ]
        if step_rows:
            self._state.executemany(
                "INSERT INTO workflow_steps "
                "(run_id, step_id, step_type, state, depends_on_json, inputs_json, "
                "output_json, error_message, started_at, finished_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                step_rows,
            )

        self._events.emit(
            run_id,
            WorkflowEventType.RUN_CREATED,
            "workflow run created",
            payload={"definition_id": definition_id, "state": RunState.PENDING.value},
        )
        return run_id

    # -- run execution -----------------------------------------------------

    def execute_run(
        self,
        run_id: str,
        *,
        block: bool = True,
        timeout: float | None = None,
    ) -> RunState:
        """Drive ``run_id`` from ``pending`` to a terminal state.

        Transitions the run to ``running`` and schedules ready steps up to the
        run's concurrency limit, persisting each step transition before the
        next is scheduled (Requirements 3.2–3.4, 3.7). When every step reaches a
        terminal state the run outcome is derived (Requirements 3.5, 3.6).

        With ``block=True`` (the default) this returns the terminal run state;
        with ``block=False`` it returns ``running`` and lets the run complete on
        background worker threads.
        """
        with self._lock:
            run = self._load_run(run_id)
            if run is None:
                raise ValueError(f"unknown workflow run '{run_id}'")
            current = RunState(run["state"])
            if current.is_terminal:
                return current
            if run_id in self._contexts:
                raise RuntimeError(f"run '{run_id}' is already executing")

            dag = self._load_dag(run_id)
            limit = int(run["concurrency_limit"]) or self._concurrency_limit
            ctx = _RunContext(
                run_id=run_id,
                dag=dag,
                concurrency_limit=max(1, limit),
                pool=ThreadPoolExecutor(
                    max_workers=max(1, limit),
                    thread_name_prefix=f"run-{run_id[:8]}",
                ),
            )
            self._contexts[run_id] = ctx
            self._set_run_state(run_id, RunState.RUNNING, mark_started=True)

        self._schedule_ready(run_id)

        if not block:
            return RunState.RUNNING

        ctx.done.wait(timeout)
        return self._current_run_state(run_id)

    # -- cancellation (Requirements 4.2, 4.3) ------------------------------

    def record_step_job(self, run_id: str, step_id: str, job_id: str) -> None:
        """Associate an in-flight step with the Kernel workload backing it.

        Step runners (the agent/sandbox-backed runners wired in by later tasks)
        call this once they have dispatched a Kernel workload so that a
        subsequent :meth:`cancel_run` can tear that workload down
        (Requirement 4.2). Calls for runs that are not actively executing are
        ignored.
        """
        with self._lock:
            ctx = self._contexts.get(run_id)
            if ctx is not None:
                ctx.jobs[step_id] = job_id

    def cancel_run(self, run_id: str, *, reason: str | None = None) -> RunState:
        """Cancel ``run_id``, tearing down any in-flight Kernel workloads.

        Stops scheduling new steps, requests teardown of every in-flight
        workload for the run, marks all not-yet-terminal steps ``cancelled``,
        and sets the run to the terminal ``cancelled`` state (Requirement 4.2).
        The method never blocks on in-flight worker threads, so the run reaches
        ``cancelled`` promptly — well within the 10s bound (Requirement 4.3);
        any worker thread that completes afterwards finds the run torn down and
        leaves the decided step state untouched.

        Cancelling an already-terminal run is a no-op that returns the run's
        current state. Raises ``ValueError`` for an unknown run.
        """
        with self._lock:
            run = self._load_run(run_id)
            if run is None:
                raise ValueError(f"unknown workflow run '{run_id}'")
            current = RunState(run["state"])
            if current.is_terminal:
                return current

            ctx = self._contexts.get(run_id)
            # Stop the scheduler from dispatching anything new for this run.
            if ctx is not None:
                ctx.finished = True

            self._set_run_state(run_id, RunState.CANCELLING)
            self._events.emit(
                run_id,
                "run.cancelling",
                "workflow run cancellation requested",
                payload={"state": RunState.CANCELLING.value, "reason": reason},
            )

            # Request teardown of every in-flight Kernel workload (Req 4.2).
            states = self._load_step_states(run_id)
            in_flight = (
                set(ctx.in_flight)
                if ctx is not None
                else {sid for sid, st in states.items() if st is StepState.RUNNING}
            )
            if self._infra is not None:
                for step_id in sorted(in_flight):
                    job_id = ctx.jobs.get(step_id, step_id) if ctx else step_id
                    try:
                        self._infra.teardown(job_id)
                    except Exception:  # noqa: BLE001 - teardown is best-effort
                        LOGGER.exception(
                            "teardown of workload '%s' (run '%s', step '%s') failed",
                            job_id,
                            run_id,
                            step_id,
                        )

            # Mark every not-yet-terminal step cancelled.
            for step_id, st in states.items():
                if not st.is_terminal:
                    self._persist_step_state(
                        run_id, step_id, StepState.CANCELLED, mark_finished=True
                    )
                    self._emit_step_state(run_id, step_id, StepState.CANCELLED)

            self._set_run_state(run_id, RunState.CANCELLED, mark_finished=True)
            self._events.emit(
                run_id,
                WorkflowEventType.RUN_CANCELLED,
                "workflow run cancelled",
                payload={"state": RunState.CANCELLED.value},
            )

            if ctx is not None:
                self._contexts.pop(run_id, None)
                ctx.done.set()
                ctx.pool.shutdown(wait=False)

        return RunState.CANCELLED

    # -- retry (Requirement 4.4) -------------------------------------------

    def retry_run(
        self,
        run_id: str,
        *,
        block: bool = True,
        timeout: float | None = None,
    ) -> RunState:
        """Re-execute the error closure of a failed run, preserving successes.

        The *error closure* is the set of steps that ended in error together
        with their transitive dependents (computed via
        :meth:`core.dag.Dag.dependents_of`). Those steps are reset to
        ``pending`` — clearing their prior output, error, and timestamps — while
        steps that already completed successfully keep their outputs untouched
        (Requirement 4.4). The run is then driven again from ``pending``.

        Only a run in the ``failed`` state can be retried; otherwise a
        ``ValueError`` is raised. Raises ``RuntimeError`` if the run is still
        executing and ``ValueError`` for an unknown run.
        """
        with self._lock:
            run = self._load_run(run_id)
            if run is None:
                raise ValueError(f"unknown workflow run '{run_id}'")
            current = RunState(run["state"])
            if current is not RunState.FAILED:
                raise ValueError(
                    f"run '{run_id}' is not failed (state={current.value}); "
                    "only failed runs can be retried"
                )
            if run_id in self._contexts:
                raise RuntimeError(f"run '{run_id}' is already executing")

            dag = self._load_dag(run_id)
            states = self._load_step_states(run_id)

            closure: set[str] = set()
            for step_id, st in states.items():
                if st is StepState.FAILED:
                    closure.add(step_id)
                    closure |= dag.dependents_of(step_id)

            for step_id in sorted(closure):
                self._reset_step(run_id, step_id)
                self._emit_step_state(run_id, step_id, StepState.PENDING)

            self._set_run_state(run_id, RunState.PENDING)
            self._events.emit(
                run_id,
                "run.retried",
                "workflow run retry requested",
                payload={
                    "state": RunState.PENDING.value,
                    "retried_steps": sorted(closure),
                },
            )

        return self.execute_run(run_id, block=block, timeout=timeout)

    # -- restart recovery (Requirements 3.7, 8.5) --------------------------

    def resume_pending_runs(self, *, block: bool = False) -> list[str]:
        """Rebuild non-terminal runs from persistence at bootstrap.

        Loads every run still in ``pending``, ``running``, or
        ``awaiting_approval`` from the :class:`DatabaseBackend` and brings it
        back under management so it survives a Control_Plane restart
        (Requirements 3.7, 8.5):

        * ``pending``/``running`` runs are resumed: any step left orphaned in a
          ``ready``/``running`` state (its Kernel workload did not survive the
          restart) is reset to ``pending`` and the run is rescheduled.
        * ``awaiting_approval`` runs are left paused for the Approval_Manager to
          resume on a user decision; they are recognized but not auto-executed.

        Returns the list of run ids that were resumed.
        """
        rows = self._state.fetch_all(
            "SELECT id, state FROM workflow_runs WHERE state IN (?, ?, ?)",
            (
                RunState.PENDING.value,
                RunState.RUNNING.value,
                RunState.AWAITING_APPROVAL.value,
            ),
        )

        resumed: list[str] = []
        for row in rows:
            run_id = row["id"]
            state = RunState(row["state"])
            if state is RunState.AWAITING_APPROVAL:
                # Preserved; the Approval_Manager resumes it on a user decision.
                resumed.append(run_id)
                continue

            # Orphaned in-flight steps lost their Kernel workloads on restart;
            # reset them so they can be rescheduled cleanly.
            self._reset_inflight_steps(run_id)
            try:
                self.execute_run(run_id, block=block)
            except RuntimeError:
                # Already executing under this process; skip re-driving it.
                pass
            resumed.append(run_id)

        return resumed

    # -- scheduling (Requirements 3.2, 3.3, 3.4) ---------------------------

    def _schedule_ready(self, run_id: str) -> None:
        """Schedule every step that is ready, up to the concurrency limit.

        A step is *ready* only when all of the steps it depends on have reached
        ``completed`` (Requirement 3.2). Ready steps are dispatched up to the
        run's concurrency limit, so independent steps may overlap but never
        exceed the bound (Requirements 3.3, 3.4). Each step's ``running``
        transition is persisted before the next step is scheduled
        (Requirement 3.7). Steps that can never become ready — because a
        dependency reached a terminal state other than ``completed`` — are
        marked ``skipped`` so the run can still reach a terminal outcome.
        """
        with self._lock:
            ctx = self._contexts.get(run_id)
            if ctx is None or ctx.finished:
                return

            states = self._load_step_states(run_id)

            # Resolve steps blocked by a failed/cancelled/skipped dependency.
            if self._skip_blocked(ctx, states):
                states = self._load_step_states(run_id)

            # If every step is terminal, derive and persist the run outcome.
            if all(state.is_terminal for state in states.values()):
                self._finish(ctx, states)
                return

            # Approval checkpoints are never dispatched to the worker pool: a
            # ready step of type "approval" enters a checkpoint (pausing it and,
            # structurally, its dependents) instead of running (Req 8.1, 8.2).
            if self._approvals is not None and self._enter_ready_checkpoints(
                ctx, states
            ):
                states = self._load_step_states(run_id)

            occupied = sum(1 for s in states.values() if s in _OCCUPYING_STATES)
            available = ctx.concurrency_limit - occupied
            if available > 0:
                for step_id in self._ready_steps(ctx.dag, states):
                    if available <= 0:
                        break
                    inputs = self._collect_inputs(run_id, ctx.dag.nodes[step_id])
                    # Persist the transition BEFORE dispatching the next step.
                    self._persist_step_state(
                        run_id, step_id, StepState.RUNNING, mark_started=True
                    )
                    self._emit_step_state(run_id, step_id, StepState.RUNNING)
                    ctx.in_flight.add(step_id)
                    available -= 1
                    ctx.pool.submit(self._execute_step, run_id, step_id, inputs)

            # When nothing is in flight and the only thing blocking further
            # progress is a checkpoint awaiting a decision, pause the run so its
            # restart-safe awaiting-approval state is preserved (Req 8.1, 8.5).
            if not ctx.in_flight and any(
                s is StepState.AWAITING_APPROVAL for s in states.values()
            ):
                self._pause_for_approval(ctx)

    def _enter_ready_checkpoints(
        self, ctx: _RunContext, states: dict[str, StepState]
    ) -> bool:
        """Enter a checkpoint for every ready approval step.

        A ready step of type ``"approval"`` is handed to the Approval_Manager,
        which sets it ``awaiting-approval``, persists the run's awaiting-approval
        state, and emits an ``approval-required`` event (Requirements 8.1, 8.2).
        ``states`` is updated in place. Returns ``True`` if any checkpoint was
        entered.
        """
        entered = False
        for step_id in self._ready_steps(ctx.dag, states):
            node = ctx.dag.nodes[step_id]
            if node.step_type != "approval":
                continue
            context = self._approval_context(ctx.run_id, node)
            self._approvals.enter_checkpoint(ctx.run_id, step_id, context)
            states[step_id] = StepState.AWAITING_APPROVAL
            entered = True
        return entered

    def _approval_context(self, run_id: str, node: DagNode) -> dict[str, Any]:
        """Build the context handed to the Approval_Manager for a checkpoint."""
        return {
            "step_id": node.step_id,
            "step_type": node.step_type,
            "config": dict(node.config),
            "inputs": self._collect_inputs(run_id, node),
        }

    def _pause_for_approval(self, ctx: _RunContext) -> None:
        """Pause a run blocked on an approval checkpoint.

        Tears down the per-run execution context (the run's awaiting-approval
        state is already persisted by the Approval_Manager) without marking the
        run terminal, so the Approval_Manager can later resume it on a user
        decision (Requirements 8.1, 8.5). A blocking :meth:`execute_run` caller
        unblocks and observes the run's ``awaiting_approval`` state.
        """
        ctx.finished = True
        self._contexts.pop(ctx.run_id, None)
        ctx.done.set()
        ctx.pool.shutdown(wait=False)

    def _on_step_complete(
        self, run_id: str, step_id: str, result: StepResult
    ) -> None:
        """Persist a step's terminal transition, then schedule what's ready.

        Persisting before re-scheduling guarantees that a restart can rebuild
        in-flight state and that the run outcome is derived only from durably
        recorded step states (Requirement 3.7).
        """
        with self._lock:
            ctx = self._contexts.get(run_id)
            # The run may have been cancelled (and its context torn down) while
            # this step's terminal transition was in flight. In that case the
            # step's final state is already decided (e.g. ``cancelled``); do not
            # overwrite it or attempt to schedule further work.
            if ctx is None or ctx.finished:
                return
            terminal = result.state if result.state.is_terminal else StepState.FAILED
            self._persist_step_state(
                run_id,
                step_id,
                terminal,
                output=result.output,
                error_message=result.error_message,
                mark_finished=True,
            )
            self._emit_step_state(
                run_id, step_id, terminal, error_message=result.error_message
            )
            if ctx is not None:
                ctx.in_flight.discard(step_id)

        # Re-evaluate readiness now that a dependency may have completed.
        self._schedule_ready(run_id)

    def _execute_step(
        self, run_id: str, step_id: str, inputs: dict[str, Any]
    ) -> None:
        """Run a single step via the injected runner and report its result.

        Any exception raised by the runner is converted into a ``failed``
        result so one misbehaving step cannot abort the whole scheduler.
        """
        ctx = self._contexts.get(run_id)
        if ctx is None:
            # The run was cancelled/torn down before this step started; nothing
            # to do (its state is already decided by cancellation).
            return
        node = ctx.dag.nodes[step_id]
        try:
            if self._step_runner is None:
                result = StepResult(
                    step_id=step_id,
                    state=StepState.FAILED,
                    error_message="no step runner configured for this executor",
                )
            else:
                result = self._step_runner(run_id, node, inputs)
        except _StopRun as stop:
            # An agent step signalled a hard stop (Req 5.5, 5.6): the offending
            # step is recorded failed and the whole run is halted.
            self._abort_run(run_id, step_id, stop.reason)
            return
        except Exception as exc:  # noqa: BLE001 - isolate step failure
            LOGGER.exception("step '%s' of run '%s' raised", step_id, run_id)
            result = StepResult(
                step_id=step_id, state=StepState.FAILED, error_message=str(exc)
            )
        self._on_step_complete(run_id, step_id, result)

    # -- agent dispatch (Requirements 5.1, 5.2, 5.3, 5.5, 5.6) -------------

    def _run_agent_step(
        self, run_id: str, node: DagNode, inputs: dict[str, Any]
    ) -> StepResult:
        """Dispatch an agent Workflow_Step via the injected Agent_Orchestrator.

        Dispatches the invocation using the agent referenced by the step's
        config (Requirement 5.1) and forwards the completed upstream outputs —
        already collected and keyed by dependency step id — as the invocation's
        inputs (Requirement 5.2).

        Outcome mapping:

        * a *pre-execution error* (missing agent reference, or the orchestrator
          raising before the invocation begins) and a *failed* invocation both
          mark the step ``failed``; the reason is recorded in the run event
          history when the step transition is emitted (Requirement 5.3);
        * an invocation that *does not execute at all* — the orchestrator
          raising :class:`InvocationNotExecutedError`, returning nothing
          dispatchable, or never reaching a terminal status — stops the whole
          run (Requirement 5.5);
        * a failure to *record the invocation event*
          (:class:`InvocationEventRecordingError`) stops the whole run
          (Requirement 5.6).

        The two run-stopping conditions are signalled by raising :class:`_StopRun`,
        which :meth:`_execute_step` catches to abort the run.
        """
        if node.step_type != "agent":
            # Tool/approval/subworkflow steps are dispatched by their own
            # subsystems (wired in by later tasks); this runner only owns agent
            # invocations.
            return StepResult(
                step_id=node.step_id,
                state=StepState.FAILED,
                error_message=(
                    f"no runner configured for step type '{node.step_type}'"
                ),
            )

        if self._agents is None:
            return StepResult(
                step_id=node.step_id,
                state=StepState.FAILED,
                error_message="no agent orchestrator configured for this executor",
            )

        agent_id = self._agent_reference(node.config)
        if not agent_id:
            # Pre-execution error before the invocation begins (Req 5.3).
            return StepResult(
                step_id=node.step_id,
                state=StepState.FAILED,
                error_message="agent step is missing an agent reference",
            )

        payload = self._build_invocation_payload(node, inputs)

        try:
            invocation = self._agents.invoke_agent(agent_id, payload)
        except InvocationEventRecordingError as exc:
            # Recording the invocation event failed -> stop the run (Req 5.6).
            raise _StopRun(
                f"invocation-event recording failed for step '{node.step_id}': {exc}"
            ) from exc
        except InvocationNotExecutedError as exc:
            # The configured invocation never ran -> stop the run (Req 5.5).
            raise _StopRun(
                f"agent invocation for step '{node.step_id}' did not execute: {exc}"
            ) from exc
        except Exception as exc:  # noqa: BLE001 - pre-execution error (Req 5.3)
            return StepResult(
                step_id=node.step_id,
                state=StepState.FAILED,
                error_message=str(exc),
            )

        if not isinstance(invocation, dict) or not invocation.get("id"):
            # Dispatch returned nothing executable -> invocation did not run.
            raise _StopRun(
                f"agent invocation for step '{node.step_id}' did not execute"
            )

        invocation = self._await_invocation(invocation)
        status = invocation.get("status")

        if status == "succeeded":
            return StepResult(
                step_id=node.step_id,
                state=StepState.COMPLETED,
                output=self._invocation_output(invocation),
                token_usage=self._invocation_tokens(invocation),
            )
        if status == "failed":
            # The agent invocation ran and failed -> step failed (Req 5.3).
            return StepResult(
                step_id=node.step_id,
                state=StepState.FAILED,
                error_message=(
                    invocation.get("errorMessage") or "agent invocation failed"
                ),
                token_usage=self._invocation_tokens(invocation),
            )

        # Never reached a terminal status -> the invocation did not execute.
        raise _StopRun(
            f"agent invocation for step '{node.step_id}' did not execute "
            f"(status={status!r})"
        )

    def _await_invocation(self, invocation: dict[str, Any]) -> dict[str, Any]:
        """Return the invocation once it reaches a terminal status.

        Agent invocations run asynchronously, so a freshly dispatched
        invocation may still be ``queued``/``running``. This polls the
        Agent_Orchestrator until the invocation is terminal or the configured
        timeout elapses, returning the latest snapshot either way.
        """
        if invocation.get("status") in _TERMINAL_INVOCATION_STATUSES:
            return invocation
        get_invocation = getattr(self._agents, "get_invocation", None)
        if not callable(get_invocation):
            return invocation

        invocation_id = invocation.get("id")
        latest = invocation
        deadline = time.monotonic() + self._agent_poll_timeout
        while True:
            fetched = get_invocation(invocation_id)
            if isinstance(fetched, dict):
                latest = fetched
                if fetched.get("status") in _TERMINAL_INVOCATION_STATUSES:
                    return fetched
            if time.monotonic() >= deadline:
                return latest
            time.sleep(self._agent_poll_interval)

    @staticmethod
    def _agent_reference(config: dict[str, Any]) -> str | None:
        """Extract the agent id a step is configured to invoke, if any."""
        for key in ("agent", "agentId", "agent_id"):
            value = config.get(key)
            if value:
                return str(value)
        return None

    @staticmethod
    def _build_invocation_payload(
        node: DagNode, inputs: dict[str, Any]
    ) -> dict[str, Any]:
        """Build the Agent_Orchestrator payload for an agent step.

        The step's own configured inputs are merged with the completed upstream
        outputs (keyed by dependency step id) so dependents see their
        predecessors' results (Requirement 5.2).
        """
        configured = node.config.get("inputs")
        payload_inputs: dict[str, Any] = (
            dict(configured) if isinstance(configured, dict) else {}
        )
        payload_inputs.update(inputs)
        payload: dict[str, Any] = {"inputs": payload_inputs}
        overrides = node.config.get("overrides")
        if isinstance(overrides, dict):
            payload["overrides"] = overrides
        return payload

    @staticmethod
    def _invocation_output(invocation: dict[str, Any]) -> dict[str, Any]:
        """Derive a step's output dict from a succeeded invocation."""
        output = invocation.get("outputJson")
        if isinstance(output, dict):
            return output
        text = invocation.get("outputText")
        return {"text": text} if text is not None else {}

    @staticmethod
    def _invocation_tokens(invocation: dict[str, Any]) -> int | None:
        """Extract total token usage from an invocation, when available."""
        usage = invocation.get("usage")
        if isinstance(usage, dict):
            for key in ("totalTokens", "total_tokens", "total"):
                value = usage.get(key)
                if isinstance(value, int):
                    return value
        return None

    def _abort_run(self, run_id: str, step_id: str, reason: str) -> None:
        """Stop a whole run because an agent step could not proceed.

        Records the offending step as ``failed`` with ``reason`` (Requirement
        5.3 recording), halts scheduling, marks every still-pending/in-flight
        step ``skipped`` so the run stops promptly, and drives the run to the
        terminal ``failed`` state with the reason recorded in the event history
        (Requirements 5.5, 5.6). Any in-flight worker that finishes afterwards
        finds the context torn down and leaves the decided state untouched.
        """
        with self._lock:
            ctx = self._contexts.get(run_id)
            if ctx is None or ctx.finished:
                return
            ctx.finished = True

            self._persist_step_state(
                run_id,
                step_id,
                StepState.FAILED,
                error_message=reason,
                mark_finished=True,
            )
            self._emit_step_state(
                run_id, step_id, StepState.FAILED, error_message=reason
            )
            ctx.in_flight.discard(step_id)

            for sid, st in self._load_step_states(run_id).items():
                if not st.is_terminal:
                    self._persist_step_state(
                        run_id, sid, StepState.SKIPPED, mark_finished=True
                    )
                    self._emit_step_state(run_id, sid, StepState.SKIPPED)

            self._set_run_state(run_id, RunState.FAILED, mark_finished=True)
            self._events.emit(
                run_id,
                WorkflowEventType.RUN_FAILED,
                "workflow run stopped",
                step_id=step_id,
                payload={"state": RunState.FAILED.value, "reason": reason},
            )

            self._contexts.pop(run_id, None)
            ctx.done.set()
            ctx.pool.shutdown(wait=False)

    # -- outcome derivation (Requirements 3.5, 3.6) ------------------------

    def _finish(self, ctx: _RunContext, states: dict[str, StepState]) -> None:
        """Derive and persist the terminal run state from the step states."""
        if ctx.finished:
            return
        ctx.finished = True
        outcome = self._derive_outcome(states)
        self._set_run_state(ctx.run_id, outcome, mark_finished=True)
        event_type = (
            WorkflowEventType.RUN_COMPLETED
            if outcome is RunState.COMPLETED
            else WorkflowEventType.RUN_FAILED
        )
        self._events.emit(
            ctx.run_id,
            event_type,
            f"workflow run {outcome.value}",
            payload={"state": outcome.value},
        )
        self._contexts.pop(ctx.run_id, None)
        ctx.done.set()
        ctx.pool.shutdown(wait=False)

    @staticmethod
    def _derive_outcome(states: dict[str, StepState]) -> RunState:
        """Return ``completed`` or ``failed`` from relevant step outcomes.

        Only ``completed`` (success) and ``failed`` (error) steps are relevant;
        a single failed step makes the run ``failed`` while ``cancelled`` and
        ``skipped`` steps never change the determination (Requirements 3.5,
        3.6). A run with no relevant steps is vacuously ``completed``.
        """
        if any(state is StepState.FAILED for state in states.values()):
            return RunState.FAILED
        return RunState.COMPLETED

    # -- readiness helpers -------------------------------------------------

    @staticmethod
    def _ready_steps(dag: Dag, states: dict[str, StepState]) -> list[str]:
        """Return pending steps whose dependencies are all ``completed``."""
        ready: list[str] = []
        for step_id in sorted(dag.nodes):
            if states.get(step_id) is not StepState.PENDING:
                continue
            deps = dag.nodes[step_id].depends_on
            if all(
                states.get(dep) is StepState.COMPLETED
                for dep in deps
                if dep in dag.nodes
            ):
                ready.append(step_id)
        return ready

    def _skip_blocked(
        self, ctx: _RunContext, states: dict[str, StepState]
    ) -> bool:
        """Mark pending steps blocked by a non-completed dependency ``skipped``.

        A step whose dependency reached a terminal state other than
        ``completed`` (failed/cancelled/skipped) can never become ready, so it
        is transitioned to ``skipped``. Returns ``True`` if any step changed.

        The skip must propagate *transitively*: when a step is skipped because
        its dependency was skipped, any step depending on it must also be
        skipped. A single ordered pass cannot guarantee this — a dependent that
        is iterated before its dependency gets skipped in the same pass would be
        left pending, and with no step left in-flight to re-trigger scheduling
        the run could deadlock short of a terminal state. To avoid that, the
        skip-propagation pass is repeated to a *fixpoint*: it loops until a full
        pass marks no further step ``skipped`` (Requirements 3.5, 3.6, 4.4).
        """
        changed = False
        while True:
            pass_changed = False
            for step_id in sorted(ctx.dag.nodes):
                if states.get(step_id) is not StepState.PENDING:
                    continue
                for dep in ctx.dag.nodes[step_id].depends_on:
                    if dep not in ctx.dag.nodes:
                        continue
                    dep_state = states.get(dep)
                    if dep_state is not None and dep_state.is_terminal and (
                        dep_state is not StepState.COMPLETED
                    ):
                        self._persist_step_state(
                            run_id=ctx.run_id,
                            step_id=step_id,
                            state=StepState.SKIPPED,
                            mark_finished=True,
                        )
                        self._emit_step_state(
                            ctx.run_id, step_id, StepState.SKIPPED
                        )
                        states[step_id] = StepState.SKIPPED
                        pass_changed = True
                        changed = True
                        break
            if not pass_changed:
                break
        return changed

    def _collect_inputs(self, run_id: str, node: DagNode) -> dict[str, Any]:
        """Gather completed upstream outputs keyed by dependency step id.

        Provides each step access to its dependencies' outputs. The richer
        agent input-flow semantics are completed by task 11; this core simply
        surfaces what has been persisted.
        """
        inputs: dict[str, Any] = {}
        for dep in node.depends_on:
            row = self._state.fetch_one(
                "SELECT output_json FROM workflow_steps "
                "WHERE run_id = ? AND step_id = ?",
                (run_id, dep),
            )
            if row is not None and row.get("output_json"):
                inputs[dep] = from_json(row["output_json"], None)
        return inputs

    # -- observation -------------------------------------------------------

    def get_run(self, run_id: str) -> dict[str, Any]:
        """Return the run's current state, step states, and event history.

        Backs the run-observation API (Requirement 4.5). Raises ``ValueError``
        for an unknown run.
        """
        run = self._load_run(run_id)
        if run is None:
            raise ValueError(f"unknown workflow run '{run_id}'")
        steps = self._state.fetch_all(
            "SELECT * FROM workflow_steps WHERE run_id = ? ORDER BY step_id ASC",
            (run_id,),
        )
        events = self._events.history(run_id)
        return {
            "run": run,
            "steps": steps,
            "events": [event.to_dict() for event in events],
        }

    # -- persistence helpers -----------------------------------------------

    def _persist_step_state(
        self,
        run_id: str,
        step_id: str,
        state: StepState,
        *,
        output: dict[str, Any] | None = None,
        error_message: str | None = None,
        mark_started: bool = False,
        mark_finished: bool = False,
    ) -> None:
        sets = ["state = ?"]
        params: list[Any] = [state.value]
        if output is not None:
            sets.append("output_json = ?")
            params.append(to_json(output))
        if error_message is not None:
            sets.append("error_message = ?")
            params.append(error_message)
        if mark_started:
            sets.append("started_at = ?")
            params.append(now_iso())
        if mark_finished:
            sets.append("finished_at = ?")
            params.append(now_iso())
        params.extend([run_id, step_id])
        self._state.execute(
            f"UPDATE workflow_steps SET {', '.join(sets)} "
            "WHERE run_id = ? AND step_id = ?",
            params,
        )

    def _reset_step(self, run_id: str, step_id: str) -> None:
        """Reset a step to ``pending``, clearing its prior run artifacts.

        Used by :meth:`retry_run` so a step in the error closure re-executes
        from a clean slate while successful steps are left untouched.
        """
        self._state.execute(
            "UPDATE workflow_steps SET state = ?, output_json = NULL, "
            "error_message = NULL, started_at = NULL, finished_at = NULL "
            "WHERE run_id = ? AND step_id = ?",
            (StepState.PENDING.value, run_id, step_id),
        )

    def _reset_inflight_steps(self, run_id: str) -> None:
        """Reset orphaned ``ready``/``running`` steps to ``pending``.

        Used by :meth:`resume_pending_runs`: a step left mid-flight by a
        restart has no surviving Kernel workload, so it must be rescheduled.
        """
        self._state.execute(
            "UPDATE workflow_steps SET state = ?, started_at = NULL "
            "WHERE run_id = ? AND state IN (?, ?)",
            (
                StepState.PENDING.value,
                run_id,
                StepState.RUNNING.value,
                StepState.READY.value,
            ),
        )

    def _set_run_state(
        self,
        run_id: str,
        state: RunState,
        *,
        mark_started: bool = False,
        mark_finished: bool = False,
    ) -> None:
        sets = ["state = ?"]
        params: list[Any] = [state.value]
        if mark_started:
            sets.append("started_at = ?")
            params.append(now_iso())
        if mark_finished:
            sets.append("finished_at = ?")
            params.append(now_iso())
        params.append(run_id)
        self._state.execute(
            f"UPDATE workflow_runs SET {', '.join(sets)} WHERE id = ?",
            params,
        )

    def _emit_step_state(
        self,
        run_id: str,
        step_id: str,
        state: StepState,
        *,
        error_message: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {"state": state.value}
        if error_message is not None:
            payload["error_message"] = error_message
        self._events.emit(
            run_id,
            WorkflowEventType.STEP_STATE_CHANGED,
            f"step {step_id} -> {state.value}",
            step_id=step_id,
            payload=payload,
        )

    # -- loaders -----------------------------------------------------------

    def _load_run(self, run_id: str) -> dict[str, Any] | None:
        return self._state.fetch_one(
            "SELECT * FROM workflow_runs WHERE id = ?", (run_id,)
        )

    def _current_run_state(self, run_id: str) -> RunState:
        run = self._load_run(run_id)
        if run is None:
            raise ValueError(f"unknown workflow run '{run_id}'")
        return RunState(run["state"])

    def _load_step_states(self, run_id: str) -> dict[str, StepState]:
        rows = self._state.fetch_all(
            "SELECT step_id, state FROM workflow_steps WHERE run_id = ?",
            (run_id,),
        )
        return {row["step_id"]: StepState(row["state"]) for row in rows}

    def _load_dag(self, run_id: str) -> Dag:
        """Rebuild the run's DAG from its persisted step rows (restart-safe)."""
        rows = self._state.fetch_all(
            "SELECT step_id, step_type, depends_on_json, inputs_json "
            "FROM workflow_steps WHERE run_id = ?",
            (run_id,),
        )
        nodes: dict[str, DagNode] = {}
        for row in rows:
            depends_on = tuple(from_json(row["depends_on_json"], []))
            config = from_json(row["inputs_json"], {}) or {}
            nodes[row["step_id"]] = DagNode(
                step_id=row["step_id"],
                step_type=row["step_type"],
                config=config,
                depends_on=depends_on,
            )
        edges = tuple(
            (dep, step_id)
            for step_id, node in nodes.items()
            for dep in node.depends_on
            if dep in nodes
        )
        return Dag(nodes=nodes, edges=edges)

    def _load_definition(self, definition_id: str) -> dict[str, Any]:
        row = self._state.fetch_one(
            "SELECT definition_json FROM workflow_definitions WHERE id = ?",
            (definition_id,),
        )
        if row is None:
            raise ValueError(f"unknown workflow definition '{definition_id}'")
        return self._serializer.deserialize(row["definition_json"])

    def _dag_from_definition(self, definition: dict[str, Any]) -> Dag:
        """Build a DAG from a (already validated) canonical definition.

        Definitions are validated by the Planner at creation time, so this
        constructs the graph structurally without re-running reference checks.
        """
        nodes: dict[str, DagNode] = {}
        for step in definition.get("steps", []):
            step_id = step["id"]
            nodes[step_id] = DagNode(
                step_id=step_id,
                step_type=step.get("type", ""),
                config=step.get("config", {}) or {},
                depends_on=tuple(step.get("dependsOn", []) or []),
            )
        edges = tuple(
            (dep, step_id)
            for step_id, node in nodes.items()
            for dep in node.depends_on
            if dep in nodes
        )
        return Dag(nodes=nodes, edges=edges)

    def _resolve_limit(
        self, definition: dict[str, Any], override: int | None
    ) -> int:
        if override is not None:
            return max(1, int(override))
        policies = definition.get("policies") or {}
        for key in ("concurrencyLimit", "concurrency_limit"):
            value = policies.get(key)
            if isinstance(value, int) and value > 0:
                return value
        return self._concurrency_limit
