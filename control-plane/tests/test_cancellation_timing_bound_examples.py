"""Example tests for the cancellation timing bound (task 10.4).

Requirement 4.3 states that when a Workflow_Run cancellation completes, the
DAG_Executor SHALL set the Workflow_Run state to ``cancelled`` within 10 seconds
of the cancellation request.

``DagExecutor.cancel_run`` is non-blocking: it stops scheduling, requests
teardown of in-flight Kernel workloads, marks not-yet-terminal steps cancelled,
and transitions the run to ``cancelled`` without waiting on the worker threads
running in-flight steps. These example tests drive a run with an in-flight
(blocking) step, request cancellation, and assert the run reaches ``cancelled``
well within the 10s bound — measured against a monotonic clock.
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
from core.helpers import now_iso
from core.orchestration_types import RunState, StepResult, StepState
from core.workflow_serializer import WorkflowSerializer

# The hard upper bound mandated by Requirement 4.3.
_CANCELLATION_BOUND_SECONDS = 10.0
# cancel_run is non-blocking, so it should return far faster than the bound.
# A generous 1s ceiling keeps the test robust on slow CI while still proving the
# call does not block on the in-flight worker threads.
_NON_BLOCKING_CEILING_SECONDS = 1.0


@pytest.fixture()
def backend(tmp_path: Path) -> SQLiteBackend:
    return SQLiteBackend(tmp_path / "cancel-timing-test.db")


def _definition(steps: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    return {"version": 1, "name": "wf", "steps": steps, **extra}


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


class _RecordingInfra:
    """Minimal infra stub recording teardown calls."""

    def __init__(self) -> None:
        self.torn_down: list[str] = []

    def teardown(self, job_id: str) -> None:
        self.torn_down.append(job_id)


def test_cancel_reaches_cancelled_within_10s_bound(backend: SQLiteBackend):
    """An in-flight run reaches ``cancelled`` well within the 10s bound (Req 4.3)."""
    steps = [{"id": f"s{i}", "type": "agent"} for i in range(3)]
    _persist_definition(backend, _definition(steps))

    started = threading.Event()
    # The step blocks for far longer than the cancellation bound, so if
    # cancel_run waited on it the elapsed time would blow past the ceiling.
    release = threading.Event()
    infra = _RecordingInfra()

    def run(run_id: str, node: DagNode, inputs: dict[str, Any]) -> StepResult:
        started.set()
        release.wait(timeout=30)
        return StepResult(node.step_id, StepState.COMPLETED, output={})

    executor = DagExecutor(
        backend, concurrency_limit=3, infra=infra, step_runner=run
    )
    run_id = executor.start_run("def-1")
    executor.execute_run(run_id, block=False)

    # Wait until at least one step is actually in-flight before cancelling.
    assert started.wait(timeout=5)

    elapsed_at_request = time.monotonic()
    final = executor.cancel_run(run_id)
    elapsed = time.monotonic() - elapsed_at_request

    # Let the blocked worker threads unwind.
    release.set()

    assert final is RunState.CANCELLED
    # Within the mandated bound (Req 4.3) ...
    assert elapsed < _CANCELLATION_BOUND_SECONDS
    # ... and, because cancel_run is non-blocking, far under it.
    assert elapsed < _NON_BLOCKING_CEILING_SECONDS

    run = backend.fetch_one("SELECT state FROM workflow_runs WHERE id = ?", (run_id,))
    assert run["state"] == RunState.CANCELLED.value


def test_cancel_does_not_block_on_long_running_step(backend: SQLiteBackend):
    """cancel_run returns promptly even while a step is blocked (Req 4.3).

    The in-flight step never completes during the test; the run must still
    transition to ``cancelled`` quickly, proving the cancellation path does not
    join on the worker thread.
    """
    _persist_definition(backend, _definition([{"id": "a", "type": "agent"}]))

    started = threading.Event()
    release = threading.Event()

    def run(run_id: str, node: DagNode, inputs: dict[str, Any]) -> StepResult:
        executor.record_step_job(run_id, node.step_id, "workload-a")
        started.set()
        release.wait(timeout=30)
        return StepResult(node.step_id, StepState.COMPLETED, output={})

    infra = _RecordingInfra()
    executor = DagExecutor(backend, infra=infra, step_runner=run)
    run_id = executor.start_run("def-1")
    executor.execute_run(run_id, block=False)
    assert started.wait(timeout=5)

    start = time.monotonic()
    final = executor.cancel_run(run_id)
    elapsed = time.monotonic() - start

    release.set()

    assert final is RunState.CANCELLED
    assert elapsed < _NON_BLOCKING_CEILING_SECONDS < _CANCELLATION_BOUND_SECONDS
    # The in-flight workload was torn down as part of cancellation (Req 4.2).
    assert infra.torn_down == ["workload-a"]
