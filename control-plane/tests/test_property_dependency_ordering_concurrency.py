"""Property-based test for dependency ordering and the concurrency bound.

# Feature: orchestration-engine-completion, Property 6: Dependency ordering and concurrency bound

Property 6 states that *for any* validated DAG and *any* concurrency limit, the
DAG_Executor:

* never begins a Workflow_Step before all of the steps it depends on have
  reached the ``completed`` state (Requirement 3.2); and
* never has more steps running concurrently than the configured concurrency
  limit (Requirements 3.3, 3.4) — while still permitting independent steps to
  overlap.

The test generates random *acyclic* Workflow_Definitions (unique step ids,
``dependsOn`` referencing only strictly-earlier steps) together with a random
concurrency limit, persists each definition through the
``workflow_definitions`` table (the way ``test_dag_executor.py`` does), and
drives a real run on a fresh temp SQLite backend. An instrumented, thread-safe
``step_runner`` records, at the instant each step's body starts, whether all of
that step's dependencies had already completed, and tracks the peak number of
steps running at the same time.

Assertions (checked after the run reaches a terminal state, so failures
observed on worker threads are not swallowed by the executor's per-step error
isolation):

* no step started before all of its dependencies were completed (Req 3.2);
* the peak concurrency never exceeded the configured limit (Req 3.3, 3.4).

**Validates: Requirements 3.2, 3.3, 3.4**
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
def dags(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a random ACYCLIC definition plus a random concurrency limit.

    Acyclicity is constructed by design: step ids are unique, and step ``i``'s
    ``dependsOn`` is drawn only from the ids of strictly-earlier steps, so the
    dependency graph can contain no cycle and no dangling edge.
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
# Instrumented, thread-safe step runner
# ---------------------------------------------------------------------------


class _Instrument:
    """Records dependency-ordering and peak-concurrency observations.

    All mutable state is guarded by a single lock so the runner is safe to call
    from the executor's worker threads. Violations are recorded rather than
    raised, because an exception thrown inside the runner would be converted to
    a ``failed`` step by the executor and never surface to the test.
    """

    def __init__(self, deps_by_step: dict[str, tuple[str, ...]]) -> None:
        self._deps = deps_by_step
        self._lock = threading.Lock()
        self._active = 0
        self.peak = 0
        self._completed: set[str] = set()
        self.order_violations: list[tuple[str, list[str]]] = []

    def run(
        self, run_id: str, node: DagNode, inputs: dict[str, Any]
    ) -> StepResult:
        # Entry: every dependency must already be completed (Req 3.2), and the
        # number of concurrently running steps must stay within the limit.
        with self._lock:
            missing = [
                dep
                for dep in self._deps.get(node.step_id, ())
                if dep not in self._completed
            ]
            if missing:
                self.order_violations.append((node.step_id, missing))
            self._active += 1
            if self._active > self.peak:
                self.peak = self._active

        # Widen the concurrency window so independent steps actually overlap.
        time.sleep(0.001)

        # Exit: mark this step completed and free its concurrency slot. The
        # executor schedules a dependent only after this step is persisted
        # completed (which happens after this runner returns), so a dependent's
        # entry check above will always see this step in ``_completed``.
        with self._lock:
            self._active -= 1
            self._completed.add(node.step_id)

        return StepResult(node.step_id, StepState.COMPLETED, output={})


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
# Property 6: Dependency ordering and concurrency bound
# ---------------------------------------------------------------------------


# deadline=None: each example does real temp-SQLite I/O and spins up worker
# threads, so per-example timing varies; the property is about ordering and the
# concurrency bound, not latency.
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(case=dags())
def test_dependency_ordering_and_concurrency_bound(
    case: dict[str, Any], tmp_path_factory
) -> None:
    definition = case["definition"]
    concurrency_limit = case["concurrency_limit"]

    deps_by_step = {
        step["id"]: tuple(step["dependsOn"]) for step in definition["steps"]
    }

    db_dir: Path = tmp_path_factory.mktemp("dep-ordering-concurrency")
    backend = SQLiteBackend(db_dir / f"exec-{uuid.uuid4().hex}.db")

    definition_id = f"def-{uuid.uuid4().hex}"
    _persist_definition(backend, definition, definition_id)

    instrument = _Instrument(deps_by_step)
    executor = DagExecutor(
        backend,
        concurrency_limit=concurrency_limit,
        step_runner=instrument.run,
    )

    run_id = executor.start_run(definition_id, concurrency_limit=concurrency_limit)
    final = executor.execute_run(run_id, timeout=30)

    # The run must reach a terminal state (every step succeeds here).
    assert final is RunState.COMPLETED

    # Req 3.2: no step began before all of its dependencies were completed.
    assert instrument.order_violations == []

    # Req 3.3 / 3.4: at no instant did more steps run than the configured limit
    # (independent steps were permitted to overlap up to that bound).
    assert instrument.peak <= concurrency_limit
