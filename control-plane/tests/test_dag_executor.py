"""Unit tests for DAG_Executor core scheduling (task 9.1).

Covers run creation (Req 3.1), ready-step scheduling honoring dependency
completion (Req 3.2), concurrency bounding (Req 3.3, 3.4), persistence of each
step transition (Req 3.7), and run-outcome derivation where only relevant
success-vs-error steps drive the outcome (Req 3.5, 3.6).

Property tests (9.2–9.5) live in their own files; these are example-based unit
tests with a deterministic, injectable step runner.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import pytest

from core.dag import DagNode
from core.database import SQLiteBackend
from core.dag_executor import DagExecutor
from core.helpers import from_json, now_iso, to_json
from core.orchestration_types import RunState, StepResult, StepState
from core.workflow_serializer import WorkflowSerializer


@pytest.fixture()
def backend(tmp_path: Path) -> SQLiteBackend:
    return SQLiteBackend(tmp_path / "executor-test.db")


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


def _success_runner(state_by_step: dict[str, StepState] | None = None):
    """A runner that completes each step, or uses a per-step state override."""
    overrides = state_by_step or {}

    def run(run_id: str, node: DagNode, inputs: dict[str, Any]) -> StepResult:
        state = overrides.get(node.step_id, StepState.COMPLETED)
        return StepResult(
            step_id=node.step_id,
            state=state,
            output={"step": node.step_id, "inputs": inputs},
        )

    return run


# ---------------------------------------------------------------------------
# start_run — Req 3.1, 3.7
# ---------------------------------------------------------------------------


def test_start_run_creates_pending_run_with_unique_id(backend: SQLiteBackend):
    _persist_definition(backend, _definition([{"id": "a", "type": "agent"}]))
    executor = DagExecutor(backend, step_runner=_success_runner())

    run_id = executor.start_run("def-1")

    run = backend.fetch_one("SELECT * FROM workflow_runs WHERE id = ?", (run_id,))
    assert run is not None
    assert run["state"] == RunState.PENDING.value
    assert run["definition_id"] == "def-1"
    assert run["started_at"] is None


def test_start_run_ids_are_unique(backend: SQLiteBackend):
    _persist_definition(backend, _definition([{"id": "a", "type": "agent"}]))
    executor = DagExecutor(backend, step_runner=_success_runner())
    ids = {executor.start_run("def-1") for _ in range(5)}
    assert len(ids) == 5


def test_start_run_persists_one_pending_step_per_node(backend: SQLiteBackend):
    definition = _definition(
        [
            {"id": "a", "type": "agent"},
            {"id": "b", "type": "agent", "dependsOn": ["a"]},
            {"id": "c", "type": "tool", "dependsOn": ["a"]},
        ]
    )
    _persist_definition(backend, definition)
    executor = DagExecutor(backend, step_runner=_success_runner())

    run_id = executor.start_run("def-1")

    rows = backend.fetch_all(
        "SELECT * FROM workflow_steps WHERE run_id = ? ORDER BY step_id", (run_id,)
    )
    assert [r["step_id"] for r in rows] == ["a", "b", "c"]
    assert all(r["state"] == StepState.PENDING.value for r in rows)
    b_row = next(r for r in rows if r["step_id"] == "b")
    assert from_json(b_row["depends_on_json"], None) == ["a"]


def test_start_run_emits_run_created_event(backend: SQLiteBackend):
    _persist_definition(backend, _definition([{"id": "a", "type": "agent"}]))
    executor = DagExecutor(backend, step_runner=_success_runner())
    run_id = executor.start_run("def-1")
    events = backend.fetch_all(
        "SELECT * FROM workflow_events WHERE run_id = ?", (run_id,)
    )
    assert any(e["type"] == "run.created" for e in events)


def test_start_run_unknown_definition_raises(backend: SQLiteBackend):
    executor = DagExecutor(backend, step_runner=_success_runner())
    with pytest.raises(ValueError):
        executor.start_run("missing")


# ---------------------------------------------------------------------------
# Dependency ordering — Req 3.2
# ---------------------------------------------------------------------------


def test_steps_execute_only_after_dependencies_complete(backend: SQLiteBackend):
    definition = _definition(
        [
            {"id": "a", "type": "agent"},
            {"id": "b", "type": "agent", "dependsOn": ["a"]},
            {"id": "c", "type": "agent", "dependsOn": ["b"]},
        ]
    )
    _persist_definition(backend, definition)

    order: list[str] = []
    lock = threading.Lock()

    def run(run_id: str, node: DagNode, inputs: dict[str, Any]) -> StepResult:
        with lock:
            order.append(node.step_id)
        return StepResult(node.step_id, StepState.COMPLETED, output={})

    executor = DagExecutor(backend, concurrency_limit=4, step_runner=run)
    run_id = executor.start_run("def-1")
    final = executor.execute_run(run_id)

    assert final is RunState.COMPLETED
    assert order == ["a", "b", "c"]


def test_dependent_receives_upstream_output(backend: SQLiteBackend):
    definition = _definition(
        [
            {"id": "a", "type": "agent"},
            {"id": "b", "type": "agent", "dependsOn": ["a"]},
        ]
    )
    _persist_definition(backend, definition)

    seen_inputs: dict[str, Any] = {}

    def run(run_id: str, node: DagNode, inputs: dict[str, Any]) -> StepResult:
        seen_inputs[node.step_id] = inputs
        return StepResult(node.step_id, StepState.COMPLETED, output={"val": node.step_id})

    executor = DagExecutor(backend, step_runner=run)
    run_id = executor.start_run("def-1")
    executor.execute_run(run_id)

    assert seen_inputs["b"]["a"] == {"val": "a"}


# ---------------------------------------------------------------------------
# Concurrency bound — Req 3.3, 3.4
# ---------------------------------------------------------------------------


def test_concurrency_limit_is_never_exceeded(backend: SQLiteBackend):
    # 6 independent steps, limit 2.
    steps = [{"id": f"s{i}", "type": "agent"} for i in range(6)]
    _persist_definition(backend, _definition(steps))

    lock = threading.Lock()
    active = 0
    peak = 0

    def run(run_id: str, node: DagNode, inputs: dict[str, Any]) -> StepResult:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.02)
        with lock:
            active -= 1
        return StepResult(node.step_id, StepState.COMPLETED, output={})

    executor = DagExecutor(backend, concurrency_limit=2, step_runner=run)
    run_id = executor.start_run("def-1")
    final = executor.execute_run(run_id)

    assert final is RunState.COMPLETED
    assert peak <= 2


def test_independent_steps_run_concurrently(backend: SQLiteBackend):
    steps = [{"id": f"s{i}", "type": "agent"} for i in range(3)]
    _persist_definition(backend, _definition(steps))

    barrier = threading.Barrier(3, timeout=5)
    overlapped = threading.Event()

    def run(run_id: str, node: DagNode, inputs: dict[str, Any]) -> StepResult:
        try:
            barrier.wait()
            overlapped.set()
        except threading.BrokenBarrierError:
            pass
        return StepResult(node.step_id, StepState.COMPLETED, output={})

    executor = DagExecutor(backend, concurrency_limit=3, step_runner=run)
    run_id = executor.start_run("def-1")
    executor.execute_run(run_id)

    # All three could only pass the barrier together if they ran concurrently.
    assert overlapped.is_set()


# ---------------------------------------------------------------------------
# Persistence of transitions — Req 3.7
# ---------------------------------------------------------------------------


def test_completed_steps_persist_terminal_state_and_output(backend: SQLiteBackend):
    definition = _definition(
        [{"id": "a", "type": "agent"}, {"id": "b", "type": "agent", "dependsOn": ["a"]}]
    )
    _persist_definition(backend, definition)
    executor = DagExecutor(backend, step_runner=_success_runner())
    run_id = executor.start_run("def-1")
    executor.execute_run(run_id)

    rows = backend.fetch_all(
        "SELECT * FROM workflow_steps WHERE run_id = ? ORDER BY step_id", (run_id,)
    )
    assert all(r["state"] == StepState.COMPLETED.value for r in rows)
    assert all(r["started_at"] and r["finished_at"] for r in rows)
    assert all(r["output_json"] for r in rows)


def test_step_transitions_emit_events(backend: SQLiteBackend):
    _persist_definition(backend, _definition([{"id": "a", "type": "agent"}]))
    executor = DagExecutor(backend, step_runner=_success_runner())
    run_id = executor.start_run("def-1")
    executor.execute_run(run_id)

    step_events = backend.fetch_all(
        "SELECT * FROM workflow_events WHERE run_id = ? AND type = 'step.state_changed'",
        (run_id,),
    )
    # At least running and completed transitions for step a.
    states = {from_json(e["payload_json"], {}).get("state") for e in step_events}
    assert StepState.RUNNING.value in states
    assert StepState.COMPLETED.value in states


# ---------------------------------------------------------------------------
# Outcome derivation — Req 3.5, 3.6
# ---------------------------------------------------------------------------


def test_all_success_yields_completed(backend: SQLiteBackend):
    steps = [{"id": f"s{i}", "type": "agent"} for i in range(4)]
    _persist_definition(backend, _definition(steps))
    executor = DagExecutor(backend, concurrency_limit=2, step_runner=_success_runner())
    run_id = executor.start_run("def-1")
    assert executor.execute_run(run_id) is RunState.COMPLETED


def test_any_error_yields_failed(backend: SQLiteBackend):
    steps = [{"id": "a", "type": "agent"}, {"id": "b", "type": "agent"}]
    _persist_definition(backend, _definition(steps))
    runner = _success_runner({"b": StepState.FAILED})
    executor = DagExecutor(backend, concurrency_limit=2, step_runner=runner)
    run_id = executor.start_run("def-1")
    assert executor.execute_run(run_id) is RunState.FAILED


def test_failed_step_skips_its_dependents(backend: SQLiteBackend):
    definition = _definition(
        [
            {"id": "a", "type": "agent"},
            {"id": "b", "type": "agent", "dependsOn": ["a"]},
            {"id": "c", "type": "agent", "dependsOn": ["b"]},
        ]
    )
    _persist_definition(backend, definition)
    runner = _success_runner({"a": StepState.FAILED})
    executor = DagExecutor(backend, step_runner=runner)
    run_id = executor.start_run("def-1")
    final = executor.execute_run(run_id)

    assert final is RunState.FAILED
    states = {
        r["step_id"]: r["state"]
        for r in backend.fetch_all(
            "SELECT step_id, state FROM workflow_steps WHERE run_id = ?", (run_id,)
        )
    }
    assert states["a"] == StepState.FAILED.value
    assert states["b"] == StepState.SKIPPED.value
    assert states["c"] == StepState.SKIPPED.value


def test_cancelled_and_skipped_steps_do_not_flip_completed(backend: SQLiteBackend):
    # A cancelled step alongside successful steps must not make the run failed.
    steps = [{"id": "a", "type": "agent"}, {"id": "b", "type": "agent"}]
    _persist_definition(backend, _definition(steps))
    runner = _success_runner({"b": StepState.CANCELLED})
    executor = DagExecutor(backend, concurrency_limit=2, step_runner=runner)
    run_id = executor.start_run("def-1")
    assert executor.execute_run(run_id) is RunState.COMPLETED


def test_empty_definition_completes(backend: SQLiteBackend):
    _persist_definition(backend, _definition([]))
    executor = DagExecutor(backend, step_runner=_success_runner())
    run_id = executor.start_run("def-1")
    assert executor.execute_run(run_id) is RunState.COMPLETED


# ---------------------------------------------------------------------------
# Observation
# ---------------------------------------------------------------------------


def test_get_run_returns_state_steps_and_events(backend: SQLiteBackend):
    _persist_definition(backend, _definition([{"id": "a", "type": "agent"}]))
    executor = DagExecutor(backend, step_runner=_success_runner())
    run_id = executor.start_run("def-1")
    executor.execute_run(run_id)

    snapshot = executor.get_run(run_id)
    assert snapshot["run"]["state"] == RunState.COMPLETED.value
    assert len(snapshot["steps"]) == 1
    assert len(snapshot["events"]) >= 1


# ---------------------------------------------------------------------------
# Cancellation — Req 4.2, 4.3 (task 10.1)
# ---------------------------------------------------------------------------


class _RecordingInfra:
    """Minimal infra stub recording teardown calls."""

    def __init__(self) -> None:
        self.torn_down: list[str] = []

    def teardown(self, job_id: str) -> None:
        self.torn_down.append(job_id)


def test_cancel_run_sets_cancelled_and_marks_steps(backend: SQLiteBackend):
    steps = [{"id": "a", "type": "agent"}, {"id": "b", "type": "agent"}]
    _persist_definition(backend, _definition(steps))
    executor = DagExecutor(backend, step_runner=_success_runner())
    run_id = executor.start_run("def-1")

    # Cancel before any execution: pending steps become cancelled.
    final = executor.cancel_run(run_id)

    assert final is RunState.CANCELLED
    run = backend.fetch_one("SELECT * FROM workflow_runs WHERE id = ?", (run_id,))
    assert run["state"] == RunState.CANCELLED.value
    assert run["finished_at"]
    states = {
        r["step_id"]: r["state"]
        for r in backend.fetch_all(
            "SELECT step_id, state FROM workflow_steps WHERE run_id = ?", (run_id,)
        )
    }
    assert states == {"a": StepState.CANCELLED.value, "b": StepState.CANCELLED.value}


def test_cancel_run_tears_down_in_flight_workloads(backend: SQLiteBackend):
    steps = [{"id": f"s{i}", "type": "agent"} for i in range(3)]
    _persist_definition(backend, _definition(steps))

    started = threading.Event()
    release = threading.Event()
    infra = _RecordingInfra()

    def run(run_id: str, node: DagNode, inputs: dict[str, Any]) -> StepResult:
        started.set()
        # Block so the steps stay in-flight while we cancel.
        release.wait(timeout=5)
        return StepResult(node.step_id, StepState.COMPLETED, output={})

    executor = DagExecutor(
        backend, concurrency_limit=3, infra=infra, step_runner=run
    )
    run_id = executor.start_run("def-1")
    executor.execute_run(run_id, block=False)
    assert started.wait(timeout=5)

    final = executor.cancel_run(run_id)
    release.set()

    assert final is RunState.CANCELLED
    # All three in-flight steps had their workloads torn down.
    assert set(infra.torn_down) == {"s0", "s1", "s2"}


def test_cancel_run_uses_recorded_job_ids(backend: SQLiteBackend):
    _persist_definition(backend, _definition([{"id": "a", "type": "agent"}]))

    started = threading.Event()
    release = threading.Event()
    infra = _RecordingInfra()

    def run(run_id: str, node: DagNode, inputs: dict[str, Any]) -> StepResult:
        executor.record_step_job(run_id, node.step_id, "workload-123")
        started.set()
        release.wait(timeout=5)
        return StepResult(node.step_id, StepState.COMPLETED, output={})

    executor = DagExecutor(backend, infra=infra, step_runner=run)
    run_id = executor.start_run("def-1")
    executor.execute_run(run_id, block=False)
    assert started.wait(timeout=5)

    executor.cancel_run(run_id)
    release.set()

    assert infra.torn_down == ["workload-123"]


def test_cancel_run_on_terminal_run_is_noop(backend: SQLiteBackend):
    _persist_definition(backend, _definition([{"id": "a", "type": "agent"}]))
    executor = DagExecutor(backend, step_runner=_success_runner())
    run_id = executor.start_run("def-1")
    assert executor.execute_run(run_id) is RunState.COMPLETED
    # Cancelling a completed run leaves it completed.
    assert executor.cancel_run(run_id) is RunState.COMPLETED


def test_cancel_run_unknown_raises(backend: SQLiteBackend):
    executor = DagExecutor(backend, step_runner=_success_runner())
    with pytest.raises(ValueError):
        executor.cancel_run("missing")


# ---------------------------------------------------------------------------
# Retry — Req 4.4 (task 10.1)
# ---------------------------------------------------------------------------


def test_retry_reexecutes_error_closure_and_preserves_successes(
    backend: SQLiteBackend,
):
    # a (ok) ; b (fail) -> c ; d independent (ok)
    definition = _definition(
        [
            {"id": "a", "type": "agent"},
            {"id": "b", "type": "agent"},
            {"id": "c", "type": "agent", "dependsOn": ["b"]},
            {"id": "d", "type": "agent"},
        ]
    )
    _persist_definition(backend, definition)

    runs: dict[str, int] = {}
    lock = threading.Lock()
    fail_b = {"value": True}

    def run(run_id: str, node: DagNode, inputs: dict[str, Any]) -> StepResult:
        with lock:
            runs[node.step_id] = runs.get(node.step_id, 0) + 1
        if node.step_id == "b" and fail_b["value"]:
            return StepResult(node.step_id, StepState.FAILED, error_message="boom")
        return StepResult(node.step_id, StepState.COMPLETED, output={"v": node.step_id})

    executor = DagExecutor(backend, concurrency_limit=4, step_runner=run)
    run_id = executor.start_run("def-1")
    assert executor.execute_run(run_id) is RunState.FAILED

    # First pass: a, b, d ran; c was skipped (its dep b failed).
    first_a = runs["a"]
    first_d = runs["d"]

    # Now let b succeed and retry.
    fail_b["value"] = False
    final = executor.retry_run(run_id)

    assert final is RunState.COMPLETED
    # b and c (the error closure) re-ran; a and d (successful) did not.
    assert runs["a"] == first_a
    assert runs["d"] == first_d
    assert runs["b"] == 2
    assert runs["c"] == 1  # was skipped first time, executed on retry

    states = {
        r["step_id"]: r["state"]
        for r in backend.fetch_all(
            "SELECT step_id, state FROM workflow_steps WHERE run_id = ?", (run_id,)
        )
    }
    assert all(v == StepState.COMPLETED.value for v in states.values())


def test_retry_non_failed_run_raises(backend: SQLiteBackend):
    _persist_definition(backend, _definition([{"id": "a", "type": "agent"}]))
    executor = DagExecutor(backend, step_runner=_success_runner())
    run_id = executor.start_run("def-1")
    executor.execute_run(run_id)  # completes
    with pytest.raises(ValueError):
        executor.retry_run(run_id)


# ---------------------------------------------------------------------------
# Restart recovery — Req 3.7, 8.5 (task 10.1)
# ---------------------------------------------------------------------------


def test_resume_pending_runs_reschedules_pending_run(backend: SQLiteBackend):
    _persist_definition(backend, _definition([{"id": "a", "type": "agent"}]))
    # Simulate a restart: a run was created (pending) but never executed.
    executor1 = DagExecutor(backend, step_runner=_success_runner())
    run_id = executor1.start_run("def-1")

    # New executor instance (fresh process) resumes from persistence.
    executor2 = DagExecutor(backend, step_runner=_success_runner())
    resumed = executor2.resume_pending_runs(block=True)

    assert run_id in resumed
    run = backend.fetch_one("SELECT state FROM workflow_runs WHERE id = ?", (run_id,))
    assert run["state"] == RunState.COMPLETED.value


def test_resume_pending_runs_resets_orphaned_running_steps(backend: SQLiteBackend):
    _persist_definition(backend, _definition([{"id": "a", "type": "agent"}]))
    executor1 = DagExecutor(backend, step_runner=_success_runner())
    run_id = executor1.start_run("def-1")
    # Simulate a crash mid-run: run is RUNNING and step a is stuck RUNNING.
    backend.execute(
        "UPDATE workflow_runs SET state = ? WHERE id = ?",
        (RunState.RUNNING.value, run_id),
    )
    backend.execute(
        "UPDATE workflow_steps SET state = ? WHERE run_id = ? AND step_id = ?",
        (StepState.RUNNING.value, run_id, "a"),
    )

    executor2 = DagExecutor(backend, step_runner=_success_runner())
    executor2.resume_pending_runs(block=True)

    run = backend.fetch_one("SELECT state FROM workflow_runs WHERE id = ?", (run_id,))
    assert run["state"] == RunState.COMPLETED.value
    step = backend.fetch_one(
        "SELECT state FROM workflow_steps WHERE run_id = ? AND step_id = ?",
        (run_id, "a"),
    )
    assert step["state"] == StepState.COMPLETED.value


def test_resume_pending_runs_leaves_awaiting_approval_paused(backend: SQLiteBackend):
    _persist_definition(backend, _definition([{"id": "a", "type": "approval"}]))
    executor1 = DagExecutor(backend, step_runner=_success_runner())
    run_id = executor1.start_run("def-1")
    backend.execute(
        "UPDATE workflow_runs SET state = ? WHERE id = ?",
        (RunState.AWAITING_APPROVAL.value, run_id),
    )

    executor2 = DagExecutor(backend, step_runner=_success_runner())
    resumed = executor2.resume_pending_runs(block=True)

    assert run_id in resumed
    run = backend.fetch_one("SELECT state FROM workflow_runs WHERE id = ?", (run_id,))
    # Still awaiting approval — not auto-executed.
    assert run["state"] == RunState.AWAITING_APPROVAL.value


def test_resume_pending_runs_ignores_terminal_runs(backend: SQLiteBackend):
    _persist_definition(backend, _definition([{"id": "a", "type": "agent"}]))
    executor1 = DagExecutor(backend, step_runner=_success_runner())
    run_id = executor1.start_run("def-1")
    executor1.execute_run(run_id)  # completes

    executor2 = DagExecutor(backend, step_runner=_success_runner())
    resumed = executor2.resume_pending_runs()
    assert run_id not in resumed
