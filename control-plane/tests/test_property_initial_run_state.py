"""Property-based test for the initial state of a Workflow_Run.

# Feature: orchestration-engine-completion, Property 7: Run state starts pending with a unique id

Property 7 states that *for any* validated Workflow_Definition, starting a run
yields a unique run identifier and an initial state of ``pending``
(Requirement 3.1).

The test generates random *valid* Workflow_Definitions (unique step ids, each
step's ``dependsOn`` referencing only strictly-earlier steps so the graph is
acyclic and has no dangling edges), persists each one through the
``workflow_definitions`` table the way ``test_dag_executor.py`` does, and then
calls :meth:`DagExecutor.start_run` *many times* against a fresh temp SQLite
backend. ``start_run`` only creates the run (it does not execute it), so every
created ``workflow_runs`` row must report ``state == 'pending'``.

Assertions:

* every returned run id is unique across the many starts (Req 3.1); and
* the persisted ``workflow_runs`` row for each start has ``state == pending``
  (Req 3.1).

**Validates: Requirements 3.1**
"""

from __future__ import annotations

import string
import uuid
from pathlib import Path
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.database import SQLiteBackend
from core.dag_executor import DagExecutor
from core.helpers import now_iso
from core.orchestration_types import RunState, StepResult, StepState
from core.workflow_serializer import WorkflowSerializer

# ---------------------------------------------------------------------------
# Strategy: random valid (acyclic) Workflow_Definitions + a number of starts
# ---------------------------------------------------------------------------

_IDENT = st.text(
    alphabet=string.ascii_letters + string.digits + "_", min_size=1, max_size=6
)


@st.composite
def valid_definitions(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a random VALID definition plus how many runs to start.

    Validity is constructed by design: step ids are unique, and step ``i``'s
    ``dependsOn`` is drawn only from the ids of strictly-earlier steps, so the
    dependency graph is acyclic and references no missing step.
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
    num_starts = draw(st.integers(min_value=2, max_value=8))
    return {"definition": definition, "num_starts": num_starts}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _success_runner(run_id: str, node, inputs: dict[str, Any]) -> StepResult:
    """A trivial runner; runs are never executed in this test, so it is unused."""
    return StepResult(node.step_id, StepState.COMPLETED, output={})


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
# Property 7: Run state starts pending with a unique id
# ---------------------------------------------------------------------------


# deadline=None: each example does real temp-SQLite I/O whose per-example timing
# varies; the property is about run-id uniqueness and the initial ``pending``
# state, not latency.
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(case=valid_definitions())
def test_initial_run_state_is_pending_with_unique_id(
    case: dict[str, Any], tmp_path_factory
) -> None:
    definition = case["definition"]
    num_starts = case["num_starts"]

    db_dir: Path = tmp_path_factory.mktemp("initial-run-state")
    backend = SQLiteBackend(db_dir / f"exec-{uuid.uuid4().hex}.db")

    definition_id = f"def-{uuid.uuid4().hex}"
    _persist_definition(backend, definition, definition_id)

    executor = DagExecutor(backend, step_runner=_success_runner)

    run_ids: list[str] = [executor.start_run(definition_id) for _ in range(num_starts)]

    # Req 3.1: every returned run id is unique across the many starts.
    assert len(set(run_ids)) == len(run_ids)

    # Req 3.1: each created run row exists and has an initial state of pending.
    for run_id in run_ids:
        row = backend.fetch_one(
            "SELECT id, state, started_at FROM workflow_runs WHERE id = ?",
            (run_id,),
        )
        assert row is not None
        assert row["state"] == RunState.PENDING.value
        # A freshly-created run has not started executing yet.
        assert row["started_at"] is None
