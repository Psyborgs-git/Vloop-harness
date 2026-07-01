"""Property-based test for the retry error closure.

# Feature: orchestration-engine-completion, Property 12: Retry re-executes exactly the error closure and preserves successes

Property 12 states that *for any* failed Workflow_Run, requesting retry:

* re-executes exactly the *error closure* — the steps that ended in error
  together with their transitive dependents (computed independently from the
  graph) — and nothing else (Requirement 4.4);
* leaves steps outside the closure that previously completed successfully
  un-rerun and with their outputs preserved (Requirement 4.4); and
* drives the run to the terminal ``completed`` state once the previously
  failing steps succeed on the retry (Requirement 4.4).

The test generates random *acyclic* Workflow_Definitions (unique step ids,
``dependsOn`` referencing only strictly-earlier steps) together with a random
subset of *initially-failing* steps. The first step is always made failing so
that — being a dependency-free root — it actually fails, guaranteeing the first
pass reaches the ``failed`` state and retry is valid.

A subtlety captured by the design (and the task note): a step only *fails* if
all of its dependencies completed; a step whose dependency failed (or was
itself skipped) is *skipped*, not failed, in the first pass. Skipped steps are
transitive dependents of some failed step, so they become part of the closure
on retry. The expected closure is therefore computed independently by:

1. simulating the first pass in topological order to learn which designated
   steps actually end ``failed`` (vs. ``skipped`` because an upstream step did
   not complete); then
2. taking those failed steps together with their transitive dependents
   (via :meth:`core.dag.Dag.dependents_of`).

The run is driven on a fresh temp SQLite backend with an instrumented,
thread-safe step runner counting executions per step. After the first pass the
failing flag is cleared so the previously-failing steps succeed on retry.

Assertions (checked after retry):

* the run reaches the terminal ``completed`` state (Req 4.4);
* the set of steps executed during the retry equals the independently-computed
  error closure — exactly the closure re-ran (Req 4.4);
* every step outside the closure was a previously-successful step that did not
  re-run and kept its persisted output unchanged (Req 4.4).

**Validates: Requirements 4.4**
"""

from __future__ import annotations

import string
import threading
import uuid
from pathlib import Path
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.dag import Dag, DagNode
from core.database import SQLiteBackend
from core.dag_executor import DagExecutor
from core.helpers import now_iso
from core.orchestration_types import RunState, StepResult, StepState
from core.workflow_serializer import WorkflowSerializer

# ---------------------------------------------------------------------------
# Strategy: random acyclic Workflow_Definitions + an initially-failing subset
# ---------------------------------------------------------------------------

_IDENT = st.text(
    alphabet=string.ascii_letters + string.digits + "_", min_size=1, max_size=6
)


@st.composite
def retryable_runs(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a random ACYCLIC definition plus an initially-failing subset.

    Acyclicity is constructed by design: step ids are unique, and step ``i``'s
    ``dependsOn`` is drawn only from the ids of strictly-earlier steps, so the
    dependency graph contains no cycle and no dangling edge.

    The first step (always a dependency-free root) is forced into the failing
    set so that it actually fails in the first pass, guaranteeing the run
    reaches ``failed`` and is therefore retryable.
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

    # The first step always fails (guarantees the first pass is FAILED); any
    # other step may independently be designated failing.
    failing = {ids[0]}
    for step_id in ids[1:]:
        if draw(st.booleans()):
            failing.add(step_id)

    definition = {
        "version": 1,
        "name": "wf",
        "objective": "",
        "inputs": {},
        "steps": steps,
        "policies": {},
    }
    concurrency_limit = draw(st.integers(min_value=1, max_value=6))
    return {
        "definition": definition,
        "failing": failing,
        "concurrency_limit": concurrency_limit,
    }


# ---------------------------------------------------------------------------
# Independent reference computations (do not use the executor's own logic)
# ---------------------------------------------------------------------------


def _simulate_first_pass(
    steps: list[dict[str, Any]], failing: set[str]
) -> dict[str, str]:
    """Compute each step's first-pass outcome in topological order.

    Steps are listed so that every ``dependsOn`` references a strictly-earlier
    step, so iterating in list order is a valid topological order. A step
    *completes* if all its deps completed and it is not designated failing;
    *fails* if all its deps completed and it is designated failing; otherwise it
    is *skipped* (an upstream dep did not complete).
    """
    deps = {step["id"]: list(step["dependsOn"]) for step in steps}
    outcome: dict[str, str] = {}
    for step in steps:
        sid = step["id"]
        if all(outcome.get(dep) == "completed" for dep in deps[sid]):
            outcome[sid] = "failed" if sid in failing else "completed"
        else:
            outcome[sid] = "skipped"
    return outcome


def _expected_closure(
    steps: list[dict[str, Any]], first_pass: dict[str, str]
) -> set[str]:
    """The error closure: failed steps plus their transitive dependents."""
    nodes = {
        step["id"]: DagNode(
            step_id=step["id"],
            step_type=step["type"],
            config=step.get("config", {}),
            depends_on=tuple(step["dependsOn"]),
        )
        for step in steps
    }
    dag = Dag(nodes=nodes)
    failed = {sid for sid, st in first_pass.items() if st == "failed"}
    closure: set[str] = set(failed)
    for sid in failed:
        closure |= dag.dependents_of(sid)
    return closure


# ---------------------------------------------------------------------------
# Instrumented, thread-safe step runner counting executions per step
# ---------------------------------------------------------------------------


class _CountingRunner:
    """Counts executions per step and fails designated steps while armed.

    While ``fail_active`` is set, any designated-failing step returns a
    ``failed`` result; once cleared (before retry) every step succeeds. All
    mutable state is guarded by a lock so the runner is safe to call from the
    executor's worker threads.
    """

    def __init__(self, failing: set[str]) -> None:
        self._failing = failing
        self._lock = threading.Lock()
        self.counts: dict[str, int] = {}
        self.fail_active = True

    def run(
        self, run_id: str, node: DagNode, inputs: dict[str, Any]
    ) -> StepResult:
        with self._lock:
            self.counts[node.step_id] = self.counts.get(node.step_id, 0) + 1
            fail = self.fail_active and node.step_id in self._failing
        if fail:
            return StepResult(
                node.step_id, StepState.FAILED, error_message="boom"
            )
        return StepResult(
            node.step_id, StepState.COMPLETED, output={"v": node.step_id}
        )

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self.counts)


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


def _step_outputs(backend: SQLiteBackend, run_id: str) -> dict[str, Any]:
    return {
        row["step_id"]: row["output_json"]
        for row in backend.fetch_all(
            "SELECT step_id, output_json FROM workflow_steps WHERE run_id = ?",
            (run_id,),
        )
    }


def _step_states(backend: SQLiteBackend, run_id: str) -> dict[str, str]:
    return {
        row["step_id"]: row["state"]
        for row in backend.fetch_all(
            "SELECT step_id, state FROM workflow_steps WHERE run_id = ?",
            (run_id,),
        )
    }


# ---------------------------------------------------------------------------
# Property 12: Retry re-executes exactly the error closure and preserves successes
# ---------------------------------------------------------------------------


# deadline=None: each example does real temp-SQLite I/O and spins up worker
# threads, so per-example timing varies; the property is about retry semantics,
# not latency.
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(case=retryable_runs())
def test_retry_reexecutes_exactly_the_error_closure(
    case: dict[str, Any], tmp_path_factory
) -> None:
    definition = case["definition"]
    failing = case["failing"]
    concurrency_limit = case["concurrency_limit"]
    steps = definition["steps"]

    # Independent reference: first-pass outcomes and the expected error closure.
    first_pass = _simulate_first_pass(steps, failing)
    closure = _expected_closure(steps, first_pass)

    db_dir: Path = tmp_path_factory.mktemp("retry-closure")
    backend = SQLiteBackend(db_dir / f"exec-{uuid.uuid4().hex}.db")

    definition_id = f"def-{uuid.uuid4().hex}"
    _persist_definition(backend, definition, definition_id)

    runner = _CountingRunner(failing)
    executor = DagExecutor(
        backend,
        concurrency_limit=concurrency_limit,
        step_runner=runner.run,
    )

    # First pass: drive the run to FAILED.
    run_id = executor.start_run(definition_id, concurrency_limit=concurrency_limit)
    first_state = executor.execute_run(run_id, timeout=30)
    assert first_state is RunState.FAILED

    # The executor's first-pass step states must match the independent model.
    assert _step_states(backend, run_id) == {
        sid: {
            "completed": StepState.COMPLETED.value,
            "failed": StepState.FAILED.value,
            "skipped": StepState.SKIPPED.value,
        }[outcome]
        for sid, outcome in first_pass.items()
    }

    counts_after_first = runner.snapshot()
    outputs_after_first = _step_outputs(backend, run_id)

    # Now let the previously-failing steps succeed and retry.
    runner.fail_active = False
    final = executor.retry_run(run_id, timeout=30)

    # Req 4.4: the run reaches the terminal completed state.
    assert final is RunState.COMPLETED

    counts_after_retry = runner.snapshot()

    # Req 4.4: exactly the error closure re-executed during the retry.
    reexecuted = {
        sid
        for sid in counts_after_retry
        if counts_after_retry[sid] > counts_after_first.get(sid, 0)
    }
    assert reexecuted == closure

    # Req 4.4: steps outside the closure are exactly the previously-successful
    # steps; none of them re-ran and each kept its persisted output.
    non_closure = set(first_pass) - closure
    outputs_after_retry = _step_outputs(backend, run_id)
    for sid in non_closure:
        assert first_pass[sid] == "completed"
        assert counts_after_retry.get(sid, 0) == counts_after_first.get(sid, 0)
        assert outputs_after_retry[sid] == outputs_after_first[sid]

    # Sanity: after a successful retry every step is completed.
    assert all(
        state == StepState.COMPLETED.value
        for state in _step_states(backend, run_id).values()
    )
