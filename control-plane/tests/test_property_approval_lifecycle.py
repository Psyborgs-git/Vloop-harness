"""Property-based test for the Approval_Checkpoint lifecycle.

# Feature: orchestration-engine-completion, Property 23: Approval lifecycle pauses, resumes, and rejects correctly

Property 23 states that *for any* acyclic Workflow_Definition containing an
approval checkpoint with downstream dependents, the Approval_Manager — wired
into the DAG_Executor — drives the checkpoint lifecycle correctly:

* **Pause + announce (Req 8.1, 8.2).** Running the definition to the checkpoint
  pauses the run: the checkpoint step is ``awaiting_approval``, the run is
  ``awaiting_approval``, and an ``approval-required`` event carrying the
  checkpoint context has been emitted.
* **Resume on approval (Req 8.3).** Approving resumes execution from the
  checkpoint; the run reaches ``completed`` and every transitive dependent of
  the checkpoint runs and completes.
* **Reject is terminal (Req 8.4).** Rejecting drives the run to the terminal
  ``rejected`` state and skips every transitive dependent of the checkpoint —
  none of them is executed.

The strategy generates random acyclic definitions (each step may depend only on
earlier steps, guaranteeing acyclicity) with exactly one approval step placed so
that at least one step depends on it. Non-approval steps run through a
deterministic success runner that records which steps actually executed, so the
"not executed" guarantee on reject can be checked directly.

**Validates: Requirements 8.1, 8.2, 8.3, 8.4**
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.approval_manager import ApprovalManager
from core.dag import DagNode
from core.database import SQLiteBackend
from core.dag_executor import DagExecutor
from core.event_router import EventRouter, WorkflowEventType
from core.helpers import now_iso
from core.orchestration_types import RunState, StepResult, StepState
from core.workflow_serializer import WorkflowSerializer


# ---------------------------------------------------------------------------
# Strategy: random acyclic definitions with one approval step + dependents
# ---------------------------------------------------------------------------


@st.composite
def approval_definitions(draw: st.DrawFn) -> dict[str, Any]:
    """Generate an acyclic definition with one approval step that has dependents.

    Steps are ordered ``s0..s{n-1}`` and a step may depend only on strictly
    earlier steps, which makes every generated graph acyclic by construction.
    One step is chosen as the ``approval`` checkpoint, positioned so that at
    least one later step exists; the step immediately after the checkpoint is
    forced to depend on it, guaranteeing the checkpoint has a downstream
    dependent.
    """
    num_steps = draw(st.integers(min_value=2, max_value=6))
    # Leave at least one step after the checkpoint so it has a dependent.
    gate_idx = draw(st.integers(min_value=0, max_value=num_steps - 2))

    steps: list[dict[str, Any]] = []
    for i in range(num_steps):
        # Each step may depend on any subset of strictly-earlier steps.
        if i == 0:
            depends_on: list[str] = []
        else:
            depends_on = draw(
                st.lists(
                    st.sampled_from([f"s{j}" for j in range(i)]),
                    max_size=i,
                    unique=True,
                )
            )
        # Force the step right after the checkpoint to depend on it so the
        # checkpoint always has at least one (transitive) dependent.
        if i == gate_idx + 1 and f"s{gate_idx}" not in depends_on:
            depends_on.append(f"s{gate_idx}")

        steps.append(
            {
                "id": f"s{i}",
                "type": "approval" if i == gate_idx else "agent",
                "dependsOn": sorted(depends_on),
            }
        )

    return {
        "definition": {"version": 1, "name": "wf", "steps": steps},
        "gate_id": f"s{gate_idx}",
        "approve": draw(st.booleans()),
        "concurrency_limit": draw(st.integers(min_value=1, max_value=4)),
    }


def _transitive_dependents(steps: list[dict[str, Any]], step_id: str) -> set[str]:
    """Return every step transitively downstream of ``step_id`` in ``steps``."""
    downstream: dict[str, set[str]] = {}
    for step in steps:
        for dep in step.get("dependsOn", []):
            downstream.setdefault(dep, set()).add(step["id"])

    result: set[str] = set()
    stack = [step_id]
    while stack:
        current = stack.pop()
        for child in downstream.get(current, ()):
            if child not in result:
                result.add(child)
                stack.append(child)
    return result


# ---------------------------------------------------------------------------
# Wiring helpers (mirrors tests/test_approval_manager.py::_build)
# ---------------------------------------------------------------------------


def _recording_runner(executed: set[str], lock: threading.Lock):
    """A success runner that records which (non-approval) steps it executed."""

    def run(run_id: str, node: DagNode, inputs: dict[str, Any]) -> StepResult:
        with lock:
            executed.add(node.step_id)
        return StepResult(
            step_id=node.step_id,
            state=StepState.COMPLETED,
            output={"step": node.step_id, "inputs": inputs},
        )

    return run


def _build(backend: SQLiteBackend, case: dict[str, Any]):
    definition = case["definition"]
    ts = now_iso()
    backend.execute(
        "INSERT INTO workflow_definitions "
        "(id, name, objective, definition_json, revision, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "def-1",
            "wf",
            "",
            WorkflowSerializer().serialize(definition),
            1,
            ts,
            ts,
        ),
    )

    executed: set[str] = set()
    lock = threading.Lock()
    events = EventRouter(backend)
    approvals = ApprovalManager(backend, events)
    executor = DagExecutor(
        backend,
        approvals=approvals,
        events=events,
        step_runner=_recording_runner(executed, lock),
        concurrency_limit=case["concurrency_limit"],
    )
    approvals.attach_executor(executor)
    return events, approvals, executor, executed


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


# ---------------------------------------------------------------------------
# Property 23
# ---------------------------------------------------------------------------


# deadline=None: each example drives a thread-pooled run whose timing varies;
# the property is about lifecycle correctness, not latency.
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@given(case=approval_definitions())
def test_approval_lifecycle_pauses_resumes_and_rejects(
    case: dict[str, Any], tmp_path_factory: pytest.TempPathFactory
) -> None:
    db_path: Path = tmp_path_factory.mktemp("approval") / "lifecycle.db"
    backend = SQLiteBackend(db_path)

    gate_id: str = case["gate_id"]
    steps: list[dict[str, Any]] = case["definition"]["steps"]
    dependents = _transitive_dependents(steps, gate_id)

    _events, approvals, executor, executed = _build(backend, case)

    run_id = executor.start_run("def-1")
    state = executor.execute_run(run_id, block=True, timeout=10)

    # -- Req 8.1: reaching the checkpoint pauses the step and the run.
    assert state is RunState.AWAITING_APPROVAL
    assert _run_state(backend, run_id) == RunState.AWAITING_APPROVAL.value
    assert _step_state(backend, run_id, gate_id) == StepState.AWAITING_APPROVAL.value

    # The approval step itself never runs through the worker runner.
    assert gate_id not in executed
    # Dependents are paused (not yet executed) while the checkpoint is pending.
    assert dependents.isdisjoint(executed)

    # -- Req 8.2: an approval-required event with context was emitted.
    rows = backend.fetch_all(
        "SELECT * FROM workflow_events WHERE run_id = ? AND type = ?",
        (run_id, WorkflowEventType.APPROVAL_REQUIRED),
    )
    assert len(rows) == 1
    assert rows[0]["step_id"] == gate_id
    pending = approvals.pending_for_run(run_id)
    assert [p["step_id"] for p in pending] == [gate_id]

    if case["approve"]:
        # -- Req 8.3: approving resumes the run; dependents run and complete.
        final = approvals.approve(run_id, gate_id, block=True, timeout=10)
        assert final is RunState.COMPLETED
        assert _run_state(backend, run_id) == RunState.COMPLETED.value
        assert _step_state(backend, run_id, gate_id) == StepState.COMPLETED.value
        for dependent in dependents:
            assert _step_state(backend, run_id, dependent) == StepState.COMPLETED.value
            assert dependent in executed
    else:
        # -- Req 8.4: rejecting is terminal and skips dependents (no execution).
        final = approvals.reject(run_id, gate_id, reason="denied")
        assert final is RunState.REJECTED
        assert _run_state(backend, run_id) == RunState.REJECTED.value
        for dependent in dependents:
            assert _step_state(backend, run_id, dependent) == StepState.SKIPPED.value
        # No transitive dependent of the checkpoint was ever executed.
        assert dependents.isdisjoint(executed)
