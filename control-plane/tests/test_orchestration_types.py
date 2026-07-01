"""Unit tests for core.orchestration_types shared dataclasses and enums."""

from __future__ import annotations

from dataclasses import fields

from core.orchestration_types import (
    Budget,
    GrantContext,
    ModelRequest,
    RoutingPolicy,
    RunScope,
    RunState,
    StepResult,
    StepState,
    ToolScope,
    ToolSpec,
    ToolsetSpec,
)


def test_run_state_values_match_schema_strings():
    assert RunState.PENDING.value == "pending"
    assert RunState.BUDGET_EXCEEDED.value == "budget_exceeded"
    assert RunState.AWAITING_APPROVAL.value == "awaiting_approval"
    # str-Enum behaves like a string for persistence.
    assert RunState.RUNNING == "running"


def test_step_state_values_match_schema_strings():
    assert StepState.READY.value == "ready"
    assert StepState.SKIPPED.value == "skipped"
    assert StepState.COMPLETED == "completed"


def test_run_state_terminal_classification():
    terminal = {
        RunState.COMPLETED,
        RunState.FAILED,
        RunState.CANCELLED,
        RunState.REJECTED,
        RunState.BUDGET_EXCEEDED,
    }
    for state in RunState:
        assert state.is_terminal == (state in terminal)


def test_step_state_terminal_classification():
    terminal = {
        StepState.COMPLETED,
        StepState.FAILED,
        StepState.CANCELLED,
        StepState.SKIPPED,
    }
    for state in StepState:
        assert state.is_terminal == (state in terminal)


def test_grant_context_holds_only_reference_fields():
    # Security invariant: no raw secret value fields exist on GrantContext.
    names = {f.name for f in fields(GrantContext)}
    assert names == {"grant_id", "session_ref"}
    grant = GrantContext(grant_id="g-1", session_ref="sess-1")
    assert grant.to_dict() == {"grant_id": "g-1", "session_ref": "sess-1"}


def test_budget_unbounded_by_default():
    b = Budget()
    assert b.remaining_tokens() is None
    assert b.remaining_cost() is None
    assert b.would_exceed(tokens=10**9, cost=10**9) is False


def test_budget_would_exceed_on_token_and_cost_limits():
    b = Budget(max_tokens=100, max_cost=1.0, used_tokens=90, used_cost=0.9)
    assert b.would_exceed(tokens=10, cost=0.0) is False  # exactly at limit
    assert b.would_exceed(tokens=11, cost=0.0) is True
    assert b.would_exceed(tokens=0, cost=0.2) is True
    assert b.remaining_tokens() == 10
    assert round(b.remaining_cost(), 2) == 0.1


def test_model_request_defaults():
    req = ModelRequest(messages=[{"role": "user", "content": "hi"}])
    assert req.model_hint is None
    assert req.cache_key == ""


def test_routing_policy_defaults_independent_lists():
    p1 = RoutingPolicy()
    p2 = RoutingPolicy()
    p1.fallback_order.append("openai")
    assert p2.fallback_order == []
    assert p1.preference == "cost"
    assert p1.max_retries == 0


def test_run_scope_optional_budget():
    scope = RunScope(run_id="r-1", definition_id="d-1")
    assert scope.budget is None
    scope2 = RunScope(run_id="r-2", definition_id="d-2", budget=Budget(max_tokens=5))
    assert scope2.budget is not None
    assert scope2.budget.max_tokens == 5


def test_tool_scope_agent_disable_takes_precedence():
    scope = ToolScope(
        agent_enabled={"fs": False, "web": True},
        run_enabled={"fs": True, "search": True},
    )
    # agent-level disable wins over run-level enable
    assert scope.is_toolset_enabled("fs") is False
    # agent-level enable
    assert scope.is_toolset_enabled("web") is True
    # only enabled at run level
    assert scope.is_toolset_enabled("search") is True
    # absent everywhere -> disabled
    assert scope.is_toolset_enabled("unknown") is False


def test_tool_spec_defaults():
    tool = ToolSpec(name="run_command", description="Run a shell command", toolset="exec")
    assert tool.mutating is False
    assert tool.input_schema == {}


def test_toolset_spec_defaults():
    ts = ToolsetSpec(id="t-1", name="filesystem")
    assert ts.tools == []


def test_step_result_serializes_enum_state():
    result = StepResult(
        step_id="s-1",
        state=StepState.COMPLETED,
        output={"value": 1},
        token_usage=42,
    )
    data = result.to_dict()
    assert data["state"] == "completed"
    assert data["output"] == {"value": 1}
    assert data["token_usage"] == 42
    assert data["error_message"] is None
