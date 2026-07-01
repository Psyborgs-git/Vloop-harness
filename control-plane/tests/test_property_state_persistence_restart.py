"""Property-based test for step-state persistence and restart survival.

# Feature: orchestration-engine-completion, Property 9: Step state persists and survives restart, including awaiting-approval

Property 9 states that *for any* Workflow_Run state (including a run paused at an
Approval_Checkpoint), persisting the run and its steps and then reconstructing
the executor from the ``DatabaseBackend`` yields step states equal to those
saved:

* a run driven to a terminal state persists every step's final state and the
  run's terminal state so they survive a Control_Plane restart (Requirement
  3.7); and
* a run paused ``awaiting_approval`` is preserved across a restart — after a
  brand-new executor calls :meth:`DagExecutor.resume_pending_runs` the run is
  still ``awaiting_approval`` and its step states are intact (Requirement 8.5).

Each example generates a random *acyclic* Workflow_Definition (unique step ids,
``dependsOn`` referencing only strictly-earlier steps) on a **real temp SQLite
file**, then takes one of two paths chosen by the generator:

* **completion path** — the run is driven to a terminal state (a random subset
  of steps is made to fail, exercising ``completed``/``failed``/``skipped``
  persistence); or
* **awaiting-approval path** — the run is paused at an approval checkpoint by
  persisting ``awaiting_approval`` on the run and one of its steps.

In both paths a snapshot of the persisted step states and run state is taken,
a **brand-new** :class:`SQLiteBackend` + :class:`DagExecutor` are constructed on
the **same file** (a genuine restart — each ``SQLiteBackend`` operation opens
its own connection), and the reconstructed state is asserted equal to the
snapshot. On the awaiting-approval path ``resume_pending_runs`` is invoked first
and the run must remain ``awaiting_approval``.

**Validates: Requirements 3.7, 8.5**
"""

from __future__ import annotations

import string
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
# Strategy: random acyclic definition + fail set + awaiting-approval flag
# ---------------------------------------------------------------------------

_IDENT = st.text(
    alphabet=string.ascii_letters + string.digits + "_", min_size=1, max_size=6
)


@st.composite
def persistence_cases(draw: st.DrawFn) -> dict[str, Any]:
    """Generate an acyclic definition plus a restart scenario.

    ``awaiting`` selects the awaiting-approval path; otherwise the run is driven
    to a terminal state with ``fail_ids`` failing (the rest succeed).
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

    awaiting = draw(st.booleans())
    fail_ids = set(
        draw(st.lists(st.sampled_from(ids), max_size=len(ids), unique=True))
    )
    concurrency_limit = draw(st.integers(min_value=1, max_value=4))
    return {
        "definition": definition,
        "ids": ids,
        "awaiting": awaiting,
        "fail_ids": fail_ids,
        "concurrency_limit": concurrency_limit,
    }


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


def _failing_runner(fail_ids: set[str]):
    """A runner that fails the steps in ``fail_ids`` and completes the rest."""

    def run(run_id: str, node: DagNode, inputs: dict[str, Any]) -> StepResult:
        if node.step_id in fail_ids:
            return StepResult(
                node.step_id, StepState.FAILED, error_message="boom"
            )
        return StepResult(node.step_id, StepState.COMPLETED, output={"v": node.step_id})

    return run


def _snapshot(backend: SQLiteBackend, run_id: str) -> dict[str, Any]:
    """Capture the persisted run state and per-step states."""
    run = backend.fetch_one(
        "SELECT state FROM workflow_runs WHERE id = ?", (run_id,)
    )
    steps = backend.fetch_all(
        "SELECT step_id, state FROM workflow_steps WHERE run_id = ?", (run_id,)
    )
    return {
        "run_state": run["state"],
        "step_states": {r["step_id"]: r["state"] for r in steps},
    }


# ---------------------------------------------------------------------------
# Property 9: Step state persists and survives restart, inc. awaiting-approval
# ---------------------------------------------------------------------------


# deadline=None: each example does real temp-SQLite file I/O on its own path and
# may spin up worker threads, so per-example timing varies; the property is
# about persisted-state integrity across a restart, not latency.
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(case=persistence_cases())
def test_step_state_persists_and_survives_restart(
    case: dict[str, Any], tmp_path_factory
) -> None:
    definition = case["definition"]
    ids = case["ids"]

    # A real SQLite file on disk: a brand-new backend on this same path is a
    # genuine restart, since every SQLiteBackend operation opens its own
    # connection and commits.
    db_dir: Path = tmp_path_factory.mktemp("state-persistence")
    db_path = db_dir / f"exec-{uuid.uuid4().hex}.db"

    backend1 = SQLiteBackend(db_path)
    definition_id = f"def-{uuid.uuid4().hex}"
    _persist_definition(backend1, definition, definition_id)

    executor1 = DagExecutor(
        backend1,
        concurrency_limit=case["concurrency_limit"],
        step_runner=_failing_runner(case["fail_ids"]),
    )
    run_id = executor1.start_run(
        definition_id, concurrency_limit=case["concurrency_limit"]
    )

    if case["awaiting"]:
        # Pause the run at an approval checkpoint: the run and one of its steps
        # are persisted as awaiting_approval (the way the Approval_Manager would
        # leave them). This is the restart-survival scenario for Req 8.5.
        paused_step = ids[0]
        backend1.execute(
            "UPDATE workflow_runs SET state = ? WHERE id = ?",
            (RunState.AWAITING_APPROVAL.value, run_id),
        )
        backend1.execute(
            "UPDATE workflow_steps SET state = ? WHERE run_id = ? AND step_id = ?",
            (StepState.AWAITING_APPROVAL.value, run_id, paused_step),
        )
    else:
        # Drive the run to a terminal state (Req 3.7).
        final = executor1.execute_run(run_id, timeout=30)
        assert final.is_terminal

    # Snapshot exactly what was persisted before the "restart".
    saved = _snapshot(backend1, run_id)

    # --- restart: brand-new backend + executor on the SAME file -----------
    backend2 = SQLiteBackend(db_path)
    executor2 = DagExecutor(
        backend2,
        concurrency_limit=case["concurrency_limit"],
        step_runner=_failing_runner(case["fail_ids"]),
    )

    if case["awaiting"]:
        # Req 8.5: resuming non-terminal runs must leave an awaiting_approval
        # run paused (recognized but not auto-executed).
        resumed = executor2.resume_pending_runs(block=True)
        assert run_id in resumed

    # Req 3.7 / 8.5: the reconstructed state equals what was saved.
    restored = _snapshot(backend2, run_id)
    assert restored["step_states"] == saved["step_states"]
    assert restored["run_state"] == saved["run_state"]

    if case["awaiting"]:
        assert restored["run_state"] == RunState.AWAITING_APPROVAL.value

    # The reconstructed executor also reports the same state via its API.
    observed = executor2.get_run(run_id)
    assert observed["run"]["state"] == saved["run_state"]
    assert {
        s["step_id"]: s["state"] for s in observed["steps"]
    } == saved["step_states"]
