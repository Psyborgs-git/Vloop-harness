"""Property-based test for cancellation behavior.

# Feature: orchestration-engine-completion, Property 11: Cancellation stops scheduling and tears down in-flight work

Property 11 states that *for any* validated DAG with one or more in-flight
Workflow_Steps, requesting cancellation of the run:

* stops scheduling new steps — no step transitions to ``running`` after the
  cancellation request (Requirement 4.2);
* requests teardown of every in-flight Kernel workload for the run
  (Requirement 4.2);
* marks every not-yet-terminal step ``cancelled``; and
* drives the run to the terminal ``cancelled`` state (Requirement 4.2).

The test generates random *acyclic* Workflow_Definitions (unique step ids,
``dependsOn`` referencing only strictly-earlier steps) together with a random
concurrency limit, persists each definition through the
``workflow_definitions`` table, and drives a real run on a fresh temp SQLite
backend using a *blocking* step runner so the scheduled root steps stay
in-flight. Each running step records the Kernel workload backing it (via
``record_step_job``) into a recording infra stub. Once the expected number of
steps are in-flight, the run is cancelled and the blocked steps are released.

The number of in-flight steps is itself randomized: it equals
``min(concurrency_limit, number_of_root_steps)`` since only the dependency-free
roots can begin while every running step is blocked.

Assertions (checked after cancellation):

* the run reaches the terminal ``cancelled`` state (persisted) (Req 4.2);
* every in-flight workload had ``infra.teardown`` requested (Req 4.2);
* no additional step ever transitioned to ``running`` after cancellation
  (no new scheduling) (Req 4.2);
* every step ends ``cancelled`` (none were allowed to complete) (Req 4.2).

**Validates: Requirements 4.2**
"""

from __future__ import annotations

import string
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.dag import DagNode
from core.database import SQLiteBackend
from core.dag_executor import DagExecutor
from core.helpers import now_iso
from core.orchestration_types import RunState, StepResult, StepState
from core.workflow_serializer import WorkflowSerializer

# ---------------------------------------------------------------------------
# Strategy: random acyclic Workflow_Definitions + a concurrency limit
# ---------------------------------------------------------------------------

_IDENT = st.text(
    alphabet=string.ascii_letters + string.digits + "_", min_size=1, max_size=6
)


@st.composite
def cancellable_runs(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a random ACYCLIC definition plus a random concurrency limit.

    Acyclicity is constructed by design: step ids are unique, and step ``i``'s
    ``dependsOn`` is drawn only from the ids of strictly-earlier steps, so the
    dependency graph contains no cycle and no dangling edge. The first step is
    always a root, guaranteeing at least one step can begin (and therefore at
    least one in-flight workload to tear down).
    """
    ids = draw(st.lists(_IDENT, min_size=1, max_size=7, unique=True))

    steps: list[dict[str, Any]] = []
    for index, step_id in enumerate(ids):
        if index > 0:
            depends_on = draw(
                st.lists(
                    st.sampled_from(ids[:index]),
                    max_size=min(3, index),
                    unique=True,
                )
            )
        else:
            depends_on = []
        steps.append(
            {
                "id": step_id,
                "type": "agent",
                "config": {},
                "dependsOn": depends_on,
            }
        )

    definition = {
        "version": 1,
        "name": "wf",
        "objective": "",
        "inputs": {},
        "steps": steps,
        "policies": {},
    }
    concurrency_limit = draw(st.integers(min_value=1, max_value=6))
    return {"definition": definition, "concurrency_limit": concurrency_limit}


# ---------------------------------------------------------------------------
# Recording infra + blocking step runner
# ---------------------------------------------------------------------------


class _RecordingInfra:
    """Minimal infra stub recording teardown requests (thread-safe)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.torn_down: list[str] = []

    def teardown(self, job_id: str) -> None:
        with self._lock:
            self.torn_down.append(job_id)


class _BlockingRunner:
    """Keeps every scheduled step in-flight until explicitly released.

    On entry each step records the Kernel workload backing it (so cancellation
    can tear it down) and then blocks on a shared release event. A condition
    variable lets the test wait until a target number of steps are in-flight
    before requesting cancellation.
    """

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self.started: list[str] = []
        self.release = threading.Event()
        # Filled in after the executor is constructed (the runner needs to call
        # record_step_job on it).
        self.executor: DagExecutor | None = None

    def run(
        self, run_id: str, node: DagNode, inputs: dict[str, Any]
    ) -> StepResult:
        assert self.executor is not None
        # Associate this in-flight step with its Kernel workload (Req 4.2).
        self.executor.record_step_job(run_id, node.step_id, f"job-{node.step_id}")
        with self._cond:
            self.started.append(node.step_id)
            self._cond.notify_all()
        # Stay in-flight until cancellation releases us.
        self.release.wait(timeout=10)
        return StepResult(node.step_id, StepState.COMPLETED, output={})

    def wait_for(self, count: int, timeout: float = 10.0) -> bool:
        deadline = time.monotonic() + timeout
        with self._cond:
            while len(self.started) < count:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._cond.wait(remaining)
            return True

    def started_snapshot(self) -> list[str]:
        with self._cond:
            return list(self.started)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _persist_definition(
    backend: SQLiteBackend, definition: dict[str, Any], definition_id: str
) -> None:
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


# ---------------------------------------------------------------------------
# Property 11: Cancellation stops scheduling and tears down in-flight work
# ---------------------------------------------------------------------------


# deadline=None: each example does real temp-SQLite I/O and spins up blocking
# worker threads, so per-example timing varies; the property is about
# cancellation semantics, not latency.
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(case=cancellable_runs())
def test_cancellation_stops_scheduling_and_tears_down_in_flight_work(
    case: dict[str, Any], tmp_path_factory
) -> None:
    definition = case["definition"]
    concurrency_limit = case["concurrency_limit"]

    steps = definition["steps"]
    num_roots = sum(1 for step in steps if not step["dependsOn"])
    # Only dependency-free roots can begin while every running step is blocked,
    # capped by the concurrency limit.
    expected_in_flight = min(concurrency_limit, num_roots)

    db_dir: Path = tmp_path_factory.mktemp("cancellation-behavior")
    backend = SQLiteBackend(db_dir / f"exec-{uuid.uuid4().hex}.db")

    definition_id = f"def-{uuid.uuid4().hex}"
    _persist_definition(backend, definition, definition_id)

    infra = _RecordingInfra()
    runner = _BlockingRunner()
    executor = DagExecutor(
        backend,
        concurrency_limit=concurrency_limit,
        infra=infra,
        step_runner=runner.run,
    )
    runner.executor = executor

    run_id = executor.start_run(definition_id, concurrency_limit=concurrency_limit)
    executor.execute_run(run_id, block=False)

    # Wait until the expected number of steps are in-flight, then cancel.
    assert runner.wait_for(expected_in_flight)
    in_flight = runner.started_snapshot()
    assert len(in_flight) == expected_in_flight

    final = executor.cancel_run(run_id)
    runner.release.set()

    # Req 4.2: the run reaches the terminal cancelled state (persisted).
    assert final is RunState.CANCELLED
    run = backend.fetch_one("SELECT state FROM workflow_runs WHERE id = ?", (run_id,))
    assert run is not None
    assert run["state"] == RunState.CANCELLED.value

    # Req 4.2: every in-flight workload had teardown requested (by recorded id).
    assert set(infra.torn_down) == {f"job-{step_id}" for step_id in in_flight}

    # Give any (erroneous) post-cancellation scheduling a chance to surface,
    # then assert no new step ever transitioned to running.
    time.sleep(0.05)
    assert set(runner.started_snapshot()) == set(in_flight)

    # Req 4.2: every step ends cancelled — none were allowed to complete.
    states = {
        row["step_id"]: row["state"]
        for row in backend.fetch_all(
            "SELECT step_id, state FROM workflow_steps WHERE run_id = ?", (run_id,)
        )
    }
    assert states
    assert all(state == StepState.CANCELLED.value for state in states.values())
