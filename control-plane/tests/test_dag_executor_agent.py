"""Unit tests for DAG_Executor agent integration (task 11.1).

Covers dispatching agent steps via the injected Agent_Orchestrator (Req 5.1),
flowing completed upstream outputs to dependent steps (Req 5.2), recording a
failed/pre-execution step as ``failed`` with its reason (Req 5.3), and stopping
the whole run when a configured invocation does not execute (Req 5.5) or when
recording the invocation event fails (Req 5.6).

These are example-based unit tests with a mock Agent_Orchestrator; the
property tests (11.2-11.4) and the broader example tests (11.5) live in their
own tasks/files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest

from core.database import SQLiteBackend
from core.dag_executor import (
    DagExecutor,
    InvocationEventRecordingError,
    InvocationNotExecutedError,
)
from core.event_router import WorkflowEventType
from core.helpers import now_iso
from core.orchestration_types import RunState, StepState
from core.workflow_serializer import WorkflowSerializer


@pytest.fixture()
def backend(tmp_path: Path) -> SQLiteBackend:
    return SQLiteBackend(tmp_path / "executor-agent-test.db")


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


class FakeAgents:
    """A mock Agent_Orchestrator returning terminal invocations synchronously."""

    def __init__(
        self, handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]]
    ) -> None:
        self._handlers = handlers
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._counter = 0

    def invoke_agent(self, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((agent_id, payload))
        handler = self._handlers[agent_id]
        return handler(payload)

    def _invocation(self, **fields: Any) -> dict[str, Any]:
        self._counter += 1
        base = {"id": f"inv-{self._counter}", "status": "succeeded"}
        base.update(fields)
        return base


def _succeed(output: dict[str, Any] | None = None, tokens: int | None = None):
    def handler(self: FakeAgents, payload: dict[str, Any]) -> dict[str, Any]:
        return self._invocation(
            status="succeeded",
            outputJson=output if output is not None else {"ok": True},
            usage={"totalTokens": tokens} if tokens is not None else None,
        )

    return handler


def test_agent_step_is_dispatched_and_run_completes(backend: SQLiteBackend):
    """Req 5.1: agent steps are dispatched via the Agent_Orchestrator."""
    _persist_definition(
        backend, _definition([{"id": "a", "type": "agent", "config": {"agent": "ag1"}}])
    )

    def handler(payload: dict[str, Any]) -> dict[str, Any]:
        return {"id": "inv-1", "status": "succeeded", "outputJson": {"v": 1}}

    agents = FakeAgents({"ag1": handler})
    executor = DagExecutor(backend, agents=agents)

    run_id = executor.start_run("def-1")
    assert executor.execute_run(run_id) is RunState.COMPLETED
    assert agents.calls and agents.calls[0][0] == "ag1"


def test_upstream_output_flows_to_dependent(backend: SQLiteBackend):
    """Req 5.2: an upstream step's output is passed as a dependent's input."""
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

    seen: dict[str, Any] = {}

    def handler_a(payload: dict[str, Any]) -> dict[str, Any]:
        return {"id": "inv-a", "status": "succeeded", "outputJson": {"from_a": 42}}

    def handler_b(payload: dict[str, Any]) -> dict[str, Any]:
        seen["b_inputs"] = payload["inputs"]
        return {"id": "inv-b", "status": "succeeded", "outputJson": {}}

    agents = FakeAgents({"ag1": handler_a, "ag2": handler_b})
    executor = DagExecutor(backend, agents=agents)

    run_id = executor.start_run("def-1")
    assert executor.execute_run(run_id) is RunState.COMPLETED
    # b receives a's output keyed by the upstream step id (Req 5.2).
    assert seen["b_inputs"]["a"] == {"from_a": 42}


def test_failed_invocation_marks_step_failed_and_records_reason(
    backend: SQLiteBackend,
):
    """Req 5.3: a failed invocation marks the step failed and records why."""
    _persist_definition(
        backend, _definition([{"id": "a", "type": "agent", "config": {"agent": "ag1"}}])
    )

    def handler(payload: dict[str, Any]) -> dict[str, Any]:
        return {"id": "inv-1", "status": "failed", "errorMessage": "model exploded"}

    agents = FakeAgents({"ag1": handler})
    executor = DagExecutor(backend, agents=agents)

    run_id = executor.start_run("def-1")
    assert executor.execute_run(run_id) is RunState.FAILED

    run = executor.get_run(run_id)
    step = next(s for s in run["steps"] if s["step_id"] == "a")
    assert step["state"] == StepState.FAILED.value
    assert step["error_message"] == "model exploded"
    # The reason is recorded in the run event history.
    assert any("model exploded" in str(e["payload"]) for e in run["events"])


def test_missing_agent_reference_is_pre_execution_failure(backend: SQLiteBackend):
    """Req 5.3: a pre-execution error marks the step failed with a reason."""
    _persist_definition(
        backend, _definition([{"id": "a", "type": "agent", "config": {}}])
    )
    agents = FakeAgents({})
    executor = DagExecutor(backend, agents=agents)

    run_id = executor.start_run("def-1")
    assert executor.execute_run(run_id) is RunState.FAILED

    run = executor.get_run(run_id)
    step = next(s for s in run["steps"] if s["step_id"] == "a")
    assert step["state"] == StepState.FAILED.value
    assert "agent reference" in (step["error_message"] or "")
    assert agents.calls == []


def test_invocation_not_executed_stops_the_run(backend: SQLiteBackend):
    """Req 5.5: an invocation that never executes stops the whole run."""
    definition = _definition(
        [
            {"id": "a", "type": "agent", "config": {"agent": "ag1"}},
            {"id": "b", "type": "agent", "config": {"agent": "ag2"}},
        ]
    )
    _persist_definition(backend, definition)

    def handler_a(payload: dict[str, Any]) -> dict[str, Any]:
        raise InvocationNotExecutedError("dispatcher unavailable")

    def handler_b(payload: dict[str, Any]) -> dict[str, Any]:
        return {"id": "inv-b", "status": "succeeded", "outputJson": {}}

    agents = FakeAgents({"ag1": handler_a, "ag2": handler_b})
    # Single slot so 'a' is dispatched first and aborts before 'b' completes.
    executor = DagExecutor(backend, agents=agents, concurrency_limit=1)

    run_id = executor.start_run("def-1")
    assert executor.execute_run(run_id) is RunState.FAILED

    run = executor.get_run(run_id)
    states = {s["step_id"]: s["state"] for s in run["steps"]}
    assert states["a"] == StepState.FAILED.value
    # The run is stopped, so the independent step never completes.
    assert states["b"] in {StepState.SKIPPED.value, StepState.PENDING.value}
    assert any(
        e["type"] == WorkflowEventType.RUN_FAILED for e in run["events"]
    )


def test_event_recording_failure_stops_the_run(backend: SQLiteBackend):
    """Req 5.6: a failure to record the invocation event stops the run."""
    _persist_definition(
        backend, _definition([{"id": "a", "type": "agent", "config": {"agent": "ag1"}}])
    )

    def handler(payload: dict[str, Any]) -> dict[str, Any]:
        raise InvocationEventRecordingError("event store down")

    agents = FakeAgents({"ag1": handler})
    executor = DagExecutor(backend, agents=agents)

    run_id = executor.start_run("def-1")
    assert executor.execute_run(run_id) is RunState.FAILED

    run = executor.get_run(run_id)
    step = next(s for s in run["steps"] if s["step_id"] == "a")
    assert step["state"] == StepState.FAILED.value
    assert "recording failed" in (step["error_message"] or "")
