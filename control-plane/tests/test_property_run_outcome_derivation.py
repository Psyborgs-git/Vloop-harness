"""Property-based test for run-outcome derivation.

# Feature: orchestration-engine-completion, Property 8: Run outcome derives only from relevant success-vs-error

Property 8 states that *for any* Workflow_Run whose steps reach terminal states,
the run is:

* ``completed`` when every *relevant* step succeeded, and
* ``failed`` when any *relevant* step ended in error,

and that terminal states which are neither success nor error (``cancelled``,
``skipped``) never change that determination (Requirements 3.5, 3.6).

The test generates random definitions of **independent** steps — each step has
no dependencies — so the forced per-step terminal state is exactly what the run
observes (no skip-cascades from a failed/cancelled dependency can perturb the
relevant-step set). Each step is assigned a random forced terminal state drawn
from ``completed`` / ``failed`` / ``cancelled`` via an injectable
``step_runner``. The definition is persisted through the
``workflow_definitions`` table and a real run is driven on a fresh temp SQLite
backend with ``deadline=None``.

Assertions (checked after the run reaches a terminal state):

* the final run state is ``failed`` *iff* at least one step ended ``failed``,
  otherwise ``completed`` (Req 3.5);
* ``cancelled`` (a terminal state that is neither success nor error) never
  flips the completed-versus-failed determination (Req 3.6).

**Validates: Requirements 3.5, 3.6**
"""

from __future__ import annotations

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

# Forced terminal states a step may be driven to. ``skipped`` is excluded as a
# *forced* state because skips arise from dependency cascades, not from a step
# body returning; independent steps here never skip. The presence of
# ``cancelled`` alongside ``completed``/``failed`` is exactly what exercises
# Requirement 3.6 (a non-success/non-error terminal must not flip the outcome).
_FORCED_STATES = (StepState.COMPLETED, StepState.FAILED, StepState.CANCELLED)


@st.composite
def outcome_cases(draw: st.DrawFn) -> dict[str, Any]:
    """Generate independent steps each with a random forced terminal state."""
    count = draw(st.integers(min_value=0, max_value=8))
    forced: dict[str, StepState] = {
        f"s{index}": draw(st.sampled_from(_FORCED_STATES))
        for index in range(count)
    }
    steps = [
        {"id": step_id, "type": "agent", "config": {}, "dependsOn": []}
        for step_id in forced
    ]
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
        "forced": forced,
        "concurrency_limit": concurrency_limit,
    }


def _make_runner(forced: dict[str, StepState]):
    """An injectable runner that drives each step to its forced terminal state."""

    def run(run_id: str, node: DagNode, inputs: dict[str, Any]) -> StepResult:
        return StepResult(
            step_id=node.step_id,
            state=forced[node.step_id],
            output={"step": node.step_id},
        )

    return run


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


# deadline=None: each example does real temp-SQLite I/O and spins up worker
# threads, so per-example timing varies; the property is about the derived
# outcome, not latency.
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(case=outcome_cases())
def test_run_outcome_derives_only_from_relevant_success_vs_error(
    case: dict[str, Any], tmp_path_factory
) -> None:
    definition = case["definition"]
    forced: dict[str, StepState] = case["forced"]
    concurrency_limit = case["concurrency_limit"]

    db_dir: Path = tmp_path_factory.mktemp("run-outcome")
    backend = SQLiteBackend(db_dir / f"exec-{uuid.uuid4().hex}.db")

    definition_id = f"def-{uuid.uuid4().hex}"
    _persist_definition(backend, definition, definition_id)

    executor = DagExecutor(
        backend,
        concurrency_limit=concurrency_limit,
        step_runner=_make_runner(forced),
    )

    run_id = executor.start_run(definition_id, concurrency_limit=concurrency_limit)
    final = executor.execute_run(run_id, timeout=30)

    # Sanity: every independent step ended in exactly its forced terminal state
    # (no skip-cascade could have perturbed the relevant-step set).
    persisted = {
        row["step_id"]: StepState(row["state"])
        for row in backend.fetch_all(
            "SELECT step_id, state FROM workflow_steps WHERE run_id = ?", (run_id,)
        )
    }
    assert persisted == forced

    any_failed = any(state is StepState.FAILED for state in forced.values())

    # Req 3.5: failed iff at least one relevant step ended in error, else
    # completed. Req 3.6: cancelled steps never flip this determination — the
    # expectation depends solely on the presence of a FAILED step.
    expected = RunState.FAILED if any_failed else RunState.COMPLETED
    assert final is expected
