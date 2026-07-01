"""Example tests for agent dispatch and run observation (task 11.5).

These example-based unit tests verify two wiring guarantees:

1. An agent step is dispatched through the injected Agent_Orchestrator and the
   run completes (Requirement 5.1). A mock orchestrator records the call so we
   can assert dispatch happened through it (and not some bypassing path).
2. ``get_run`` returns the run-observation API shape: the run row with its
   current state, the list of step rows with their states, and the ordered
   event history for the run (Requirement 4.5).

Property tests (11.2-11.4) live in their own files; this file holds the
example-based coverage for tasks 11.5. A temporary SQLite backend is used so
the tests exercise the real persistence path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from core.database import SQLiteBackend
from core.dag_executor import DagExecutor
from core.event_router import WorkflowEventType
from core.helpers import now_iso
from core.orchestration_types import RunState, StepState
from core.workflow_serializer import WorkflowSerializer


@pytest.fixture()
def backend(tmp_path: Path) -> SQLiteBackend:
    return SQLiteBackend(tmp_path / "agent-dispatch-observation.db")


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


def _definition(steps: list[dict[str, Any]]) -> dict[str, Any]:
    return {"version": 1, "name": "wf", "steps": steps}


class RecordingAgents:
    """A mock Agent_Orchestrator that records every dispatch call.

    Returns a terminal, succeeded invocation synchronously so the executor can
    drive the run to completion deterministically.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def invoke_agent(self, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((agent_id, payload))
        return {
            "id": f"inv-{len(self.calls)}",
            "status": "succeeded",
            "outputJson": {"agent": agent_id},
        }


# ---------------------------------------------------------------------------
# Requirement 5.1: agent-step dispatch is wired through the Agent_Orchestrator
# ---------------------------------------------------------------------------


def test_agent_step_dispatches_through_orchestrator_and_run_completes(
    backend: SQLiteBackend,
):
    """Req 5.1: the configured agent step is dispatched via the orchestrator."""
    _persist_definition(
        backend,
        _definition([{"id": "a", "type": "agent", "config": {"agent": "ag1"}}]),
    )

    agents = RecordingAgents()
    executor = DagExecutor(backend, agents=agents)

    run_id = executor.start_run("def-1")
    outcome = executor.execute_run(run_id)

    # The run completes.
    assert outcome is RunState.COMPLETED
    # Dispatch went through the injected Agent_Orchestrator for the configured agent.
    assert len(agents.calls) == 1
    assert agents.calls[0][0] == "ag1"


def test_every_agent_step_dispatches_once_through_orchestrator(backend: SQLiteBackend):
    """Req 5.1: each agent step in the DAG is dispatched through the orchestrator."""
    definition = _definition(
        [
            {"id": "a", "type": "agent", "config": {"agent": "ag1"}},
            {
                "id": "b",
                "type": "agent",
                "config": {"agent": "ag2"},
                "dependsOn": ["a"],
            },
        ]
    )
    _persist_definition(backend, definition)

    agents = RecordingAgents()
    executor = DagExecutor(backend, agents=agents)

    run_id = executor.start_run("def-1")
    assert executor.execute_run(run_id) is RunState.COMPLETED

    dispatched = [agent_id for agent_id, _ in agents.calls]
    assert dispatched == ["ag1", "ag2"]


# ---------------------------------------------------------------------------
# Requirement 4.5: run-observation API shape (state, step states, events)
# ---------------------------------------------------------------------------


def test_get_run_returns_state_step_states_and_event_history(backend: SQLiteBackend):
    """Req 4.5: get_run returns the run row, step rows, and ordered events."""
    definition = _definition(
        [
            {"id": "a", "type": "agent", "config": {"agent": "ag1"}},
            {
                "id": "b",
                "type": "agent",
                "config": {"agent": "ag2"},
                "dependsOn": ["a"],
            },
        ]
    )
    _persist_definition(backend, definition)

    agents = RecordingAgents()
    executor = DagExecutor(backend, agents=agents)

    run_id = executor.start_run("def-1")
    assert executor.execute_run(run_id) is RunState.COMPLETED

    observation = executor.get_run(run_id)

    # The observation carries the three documented sections.
    assert set(observation) >= {"run", "steps", "events"}

    # 1) The run row with its current state.
    run = observation["run"]
    assert run["id"] == run_id
    assert run["state"] == RunState.COMPLETED.value

    # 2) The list of step rows with their states.
    steps = observation["steps"]
    assert {s["step_id"] for s in steps} == {"a", "b"}
    states = {s["step_id"]: s["state"] for s in steps}
    assert states["a"] == StepState.COMPLETED.value
    assert states["b"] == StepState.COMPLETED.value

    # 3) The ordered event history for the run.
    events = observation["events"]
    assert len(events) >= 2
    seqs = [e["seq"] for e in events]
    assert seqs == sorted(seqs)
    # Every event is attributed to this run.
    assert all(e["run_id"] == run_id for e in events)
    # Lifecycle endpoints are present: creation and completion.
    event_types = {e["type"] for e in events}
    assert WorkflowEventType.RUN_CREATED in event_types
    assert WorkflowEventType.RUN_COMPLETED in event_types


def test_get_run_observes_a_failed_run_state_and_step(backend: SQLiteBackend):
    """Req 4.5: observation reflects a failed run's state, step, and events."""
    _persist_definition(
        backend,
        # Missing agent reference triggers a pre-execution failure.
        _definition([{"id": "a", "type": "agent", "config": {}}]),
    )

    agents = RecordingAgents()
    executor = DagExecutor(backend, agents=agents)

    run_id = executor.start_run("def-1")
    assert executor.execute_run(run_id) is RunState.FAILED

    observation = executor.get_run(run_id)
    assert observation["run"]["state"] == RunState.FAILED.value
    step = next(s for s in observation["steps"] if s["step_id"] == "a")
    assert step["state"] == StepState.FAILED.value
    assert WorkflowEventType.RUN_FAILED in {e["type"] for e in observation["events"]}


def test_get_run_rejects_unknown_run(backend: SQLiteBackend):
    """Req 4.5: observing an unknown run raises rather than returning a shell."""
    executor = DagExecutor(backend, agents=RecordingAgents())
    with pytest.raises(ValueError):
        executor.get_run("does-not-exist")
