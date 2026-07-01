"""Unit tests for the Approval_Manager and its DAG_Executor wiring (task 12.1).

Covers the approval-checkpoint lifecycle (Requirement 8):

* reaching a checkpoint pauses the step and run at ``awaiting-approval`` and
  emits an ``approval-required`` event with context (Req 8.1, 8.2);
* the awaiting-approval state is persisted so it survives a restart (Req 8.5);
* approving resumes execution from the checkpoint (Req 8.3);
* rejecting drives the run to terminal ``rejected`` and skips dependents
  without executing them (Req 8.4).

Property test 23 (task 12.2) lives in its own file; these are example-based
unit tests with a deterministic, injectable step runner.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from core.approval_manager import ApprovalManager
from core.dag import DagNode
from core.dag_executor import DagExecutor
from core.database import SQLiteBackend
from core.event_router import EventRouter, WorkflowEventType
from core.helpers import now_iso
from core.orchestration_types import RunState, StepResult, StepState
from core.workflow_serializer import WorkflowSerializer


@pytest.fixture()
def backend(tmp_path: Path) -> SQLiteBackend:
    return SQLiteBackend(tmp_path / "approval-test.db")


def _persist_definition(
    backend: SQLiteBackend, definition: dict[str, Any], definition_id: str = "def-1"
) -> str:
    ts = now_iso()
    backend.execute(
        "INSERT INTO workflow_definitions "
        "(id, name, objective, definition_json, revision, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            definition_id,
            definition.get("name", "wf"),
            definition.get("objective", ""),
            WorkflowSerializer().serialize(definition),
            1,
            ts,
            ts,
        ),
    )
    return definition_id


def _definition(steps: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    return {"version": 1, "name": "wf", "steps": steps, **extra}


def _success_runner():
    """Completes each (non-approval) step, recording its inputs as output."""

    def run(run_id: str, node: DagNode, inputs: dict[str, Any]) -> StepResult:
        return StepResult(
            step_id=node.step_id,
            state=StepState.COMPLETED,
            output={"step": node.step_id, "inputs": inputs},
        )

    return run


def _build(backend: SQLiteBackend, definition: dict[str, Any], **kwargs: Any):
    """Wire an EventRouter, ApprovalManager, and DagExecutor against ``backend``."""
    _persist_definition(backend, definition)
    events = EventRouter(backend)
    approvals = ApprovalManager(backend, events)
    executor = DagExecutor(
        backend,
        approvals=approvals,
        events=events,
        step_runner=_success_runner(),
        **kwargs,
    )
    approvals.attach_executor(executor)
    return events, approvals, executor


def _step_state(backend: SQLiteBackend, run_id: str, step_id: str) -> str:
    row = backend.fetch_one(
        "SELECT state FROM workflow_steps WHERE run_id = ? AND step_id = ?",
        (run_id, step_id),
    )
    assert row is not None
    return row["state"]


def _run_state(backend: SQLiteBackend, run_id: str) -> str:
    row = backend.fetch_one("SELECT state FROM workflow_runs WHERE id = ?", (run_id,))
    assert row is not None
    return row["state"]


# Chain: prep (agent) -> gate (approval) -> finish (agent).
_CHAIN = _definition(
    [
        {"id": "prep", "type": "agent"},
        {"id": "gate", "type": "approval", "dependsOn": ["prep"]},
        {"id": "finish", "type": "agent", "dependsOn": ["gate"]},
    ]
)


# ---------------------------------------------------------------------------
# enter_checkpoint — Req 8.1, 8.2, 8.5
# ---------------------------------------------------------------------------


def test_reaching_checkpoint_pauses_run_and_step(backend: SQLiteBackend):
    _events, _approvals, executor = _build(backend, _CHAIN)

    run_id = executor.start_run("def-1")
    state = executor.execute_run(run_id, block=True, timeout=5)

    assert state is RunState.AWAITING_APPROVAL
    assert _run_state(backend, run_id) == RunState.AWAITING_APPROVAL.value
    assert _step_state(backend, run_id, "prep") == StepState.COMPLETED.value
    assert _step_state(backend, run_id, "gate") == StepState.AWAITING_APPROVAL.value
    # The dependent is paused (never scheduled) while the checkpoint is pending.
    assert _step_state(backend, run_id, "finish") == StepState.PENDING.value


def test_reaching_checkpoint_emits_approval_required_with_context(
    backend: SQLiteBackend,
):
    _events, _approvals, executor = _build(backend, _CHAIN)
    run_id = executor.start_run("def-1")
    executor.execute_run(run_id, block=True, timeout=5)

    rows = backend.fetch_all(
        "SELECT * FROM workflow_events WHERE run_id = ? AND type = ?",
        (run_id, WorkflowEventType.APPROVAL_REQUIRED),
    )
    assert len(rows) == 1
    assert rows[0]["step_id"] == "gate"


def test_pending_for_run_lists_awaiting_checkpoint(backend: SQLiteBackend):
    _events, approvals, executor = _build(backend, _CHAIN)
    run_id = executor.start_run("def-1")
    executor.execute_run(run_id, block=True, timeout=5)

    pending = approvals.pending_for_run(run_id)
    assert [p["step_id"] for p in pending] == ["gate"]
    # The checkpoint context carries the upstream output (Req 8.2).
    assert pending[0]["context"]["inputs"]["prep"]["step"] == "prep"


def test_awaiting_approval_survives_restart(backend: SQLiteBackend):
    """A fresh executor (simulating a restart) preserves the pending approval."""
    _events, _approvals, executor = _build(backend, _CHAIN)
    run_id = executor.start_run("def-1")
    executor.execute_run(run_id, block=True, timeout=5)

    # Rebuild the subsystems against the same persistent backend.
    events2 = EventRouter(backend)
    approvals2 = ApprovalManager(backend, events2)
    executor2 = DagExecutor(
        backend, approvals=approvals2, events=events2, step_runner=_success_runner()
    )
    approvals2.attach_executor(executor2)

    resumed = executor2.resume_pending_runs()
    assert run_id in resumed
    # Still paused, not auto-executed.
    assert _run_state(backend, run_id) == RunState.AWAITING_APPROVAL.value
    assert approvals2.pending_for_run(run_id)[0]["step_id"] == "gate"


# ---------------------------------------------------------------------------
# approve — Req 8.3
# ---------------------------------------------------------------------------


def test_approve_resumes_run_from_checkpoint(backend: SQLiteBackend):
    _events, approvals, executor = _build(backend, _CHAIN)
    run_id = executor.start_run("def-1")
    executor.execute_run(run_id, block=True, timeout=5)

    state = approvals.approve(run_id, "gate", block=True, timeout=5)

    assert state is RunState.COMPLETED
    assert _step_state(backend, run_id, "gate") == StepState.COMPLETED.value
    assert _step_state(backend, run_id, "finish") == StepState.COMPLETED.value


def test_approve_edits_flow_to_dependents(backend: SQLiteBackend):
    _events, approvals, executor = _build(backend, _CHAIN)
    run_id = executor.start_run("def-1")
    executor.execute_run(run_id, block=True, timeout=5)

    approvals.approve(run_id, "gate", edits={"note": "ok"}, block=True, timeout=5)

    finish = backend.fetch_one(
        "SELECT output_json FROM workflow_steps WHERE run_id = ? AND step_id = ?",
        (run_id, "finish"),
    )
    assert finish is not None
    assert '"edits"' in finish["output_json"]


def test_approve_rejects_step_not_awaiting(backend: SQLiteBackend):
    _events, approvals, executor = _build(backend, _CHAIN)
    run_id = executor.start_run("def-1")
    executor.execute_run(run_id, block=True, timeout=5)

    with pytest.raises(ValueError):
        approvals.approve(run_id, "prep")


# ---------------------------------------------------------------------------
# reject — Req 8.4
# ---------------------------------------------------------------------------


def test_reject_terminates_run_and_skips_dependents(backend: SQLiteBackend):
    _events, approvals, executor = _build(backend, _CHAIN)
    run_id = executor.start_run("def-1")
    executor.execute_run(run_id, block=True, timeout=5)

    state = approvals.reject(run_id, "gate", reason="not allowed")

    assert state is RunState.REJECTED
    assert _run_state(backend, run_id) == RunState.REJECTED.value
    # The dependent never executed.
    assert _step_state(backend, run_id, "finish") == StepState.SKIPPED.value
    # The checkpoint itself is recorded terminal with the reason.
    gate = backend.fetch_one(
        "SELECT state, error_message FROM workflow_steps "
        "WHERE run_id = ? AND step_id = ?",
        (run_id, "gate"),
    )
    assert gate["state"] == StepState.CANCELLED.value
    assert gate["error_message"] == "not allowed"


def test_reject_emits_run_rejected_event(backend: SQLiteBackend):
    _events, approvals, executor = _build(backend, _CHAIN)
    run_id = executor.start_run("def-1")
    executor.execute_run(run_id, block=True, timeout=5)

    approvals.reject(run_id, "gate", reason="nope")

    rows = backend.fetch_all(
        "SELECT * FROM workflow_events WHERE run_id = ? AND type = ?",
        (run_id, WorkflowEventType.RUN_REJECTED),
    )
    assert len(rows) == 1


def test_reject_skips_transitive_dependents(backend: SQLiteBackend):
    definition = _definition(
        [
            {"id": "gate", "type": "approval"},
            {"id": "b", "type": "agent", "dependsOn": ["gate"]},
            {"id": "c", "type": "agent", "dependsOn": ["b"]},
        ]
    )
    _events, approvals, executor = _build(backend, definition)
    run_id = executor.start_run("def-1")
    executor.execute_run(run_id, block=True, timeout=5)

    approvals.reject(run_id, "gate", reason="stop")

    assert _step_state(backend, run_id, "b") == StepState.SKIPPED.value
    assert _step_state(backend, run_id, "c") == StepState.SKIPPED.value
