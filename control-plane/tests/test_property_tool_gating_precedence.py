"""Property-based test for tool gating precedence and denial recording.

# Feature: orchestration-engine-completion, Property 24: Tool gating with agent-level precedence and recorded denials

Property 24 states that *for any* combination of agent-level and run-level
toolset enable/disable maps:

* an agent-level *disable* always wins over a run-level *enable* so agent-level
  restrictions take precedence (Requirement 9.3);
* enablement otherwise resolves correctly from the agent/run maps — a toolset is
  enabled only when it is not disabled at the agent level and is enabled at
  either the agent or run level (Requirement 9.2); and
* invoking a tool whose toolset is not enabled in the current scope is denied and
  the denial is recorded in the Workflow_Run event history via the Event_Router
  (Requirement 9.4).

The test drives :class:`core.tool_registry.ToolRegistry` over randomly generated
agent/run enable-disable maps against a real temp SQLite-backed
:class:`core.event_router.EventRouter`, then reads back the *persisted*
``workflow_events`` history to confirm denials are recorded.

**Validates: Requirements 9.2, 9.3, 9.4**
"""

from __future__ import annotations

import uuid
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.database import SQLiteBackend
from core.event_router import EventRouter, WorkflowEventType
from core.orchestration_types import (
    RunScope,
    ToolScope,
    ToolSpec,
)
from core.tool_registry import ToolRegistry

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# A small, fixed pool of toolset names so the agent/run maps overlap and exercise
# the precedence rule rather than always referencing disjoint toolsets.
_TOOLSET_NAMES = ("search", "filesystem", "network", "shell", "data")

# Each map entry is True (enabled), False (disabled), or absent (unset). Modeling
# all three states is what makes agent-level precedence observable.
_enablement = st.sampled_from([True, False])


@st.composite
def tool_scopes(draw: st.DrawFn) -> ToolScope:
    """Generate a random :class:`ToolScope` with agent/run enable-disable maps.

    Both maps are keyed by a subset of the shared toolset pool, each mapped to an
    explicit enabled/disabled boolean. Keys may appear in one map, both, or
    neither, so the generated scopes cover every precedence combination:
    agent-disable vs run-enable, agent-enable, run-only, and unset.
    """
    agent_enabled = draw(
        st.dictionaries(
            st.sampled_from(_TOOLSET_NAMES), _enablement, max_size=len(_TOOLSET_NAMES)
        )
    )
    run_enabled = draw(
        st.dictionaries(
            st.sampled_from(_TOOLSET_NAMES), _enablement, max_size=len(_TOOLSET_NAMES)
        )
    )
    return ToolScope(agent_enabled=agent_enabled, run_enabled=run_enabled)


def _expected_enabled(scope: ToolScope, toolset: str) -> bool:
    """Reference resolution of enablement, independent of the implementation.

    Agent-level disable wins; otherwise agent-level enable wins; otherwise the
    run-level value applies, defaulting to disabled when unset.
    """
    if scope.agent_enabled.get(toolset) is False:
        return False
    if scope.agent_enabled.get(toolset) is True:
        return True
    return scope.run_enabled.get(toolset, False)


def _fresh_registry(
    tmp_path: Path,
) -> tuple[ToolRegistry, EventRouter, SQLiteBackend]:
    backend = SQLiteBackend(tmp_path / f"tool-gating-{uuid.uuid4().hex}.db")
    router = EventRouter(backend)
    # A no-op sandbox executor so enabled mutating tools never fall through to a
    # routing-blocked error; this test is about gating, not sandbox routing.
    registry = ToolRegistry(
        event_router=router,
        sandbox_executor=lambda tool, args, run_scope: {"ran": tool.name},
    )
    # Register one non-mutating tool per toolset so an enabled invocation
    # succeeds and a disabled one is denied.
    for toolset in _TOOLSET_NAMES:
        registry.register_tool(
            ToolSpec(
                name=f"tool_{toolset}",
                description=f"tool in {toolset}",
                toolset=toolset,
            ),
            handler=lambda args, toolset=toolset: {"toolset": toolset},
        )
    return registry, router, backend


# ---------------------------------------------------------------------------
# Property 24: Tool gating with agent-level precedence and recorded denials
# ---------------------------------------------------------------------------


@settings(
    max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow]
)
@given(scope=tool_scopes())
def test_tool_gating_precedence_and_denial_recording(
    scope: ToolScope, tmp_path_factory
) -> None:
    """Agent-level disable beats run-level enable, enablement resolves correctly,
    and every denied invocation is recorded in the run event history."""
    base: Path = tmp_path_factory.mktemp("tool-gating")
    registry, router, _ = _fresh_registry(base)
    run_id = f"run-{uuid.uuid4().hex}"
    run_scope = RunScope(run_id=run_id, definition_id="def-1")

    expected_denials = 0

    for toolset in _TOOLSET_NAMES:
        tool_name = f"tool_{toolset}"
        expected = _expected_enabled(scope, toolset)

        # Requirements 9.2/9.3: is_enabled resolves with agent-level precedence.
        assert registry.is_enabled(tool_name, scope) == expected

        # Requirement 9.3: an agent-level disable always wins over a run-level
        # enable.
        if scope.agent_enabled.get(toolset) is False:
            assert registry.is_enabled(tool_name, scope) is False

        result = registry.invoke(tool_name, {}, scope, run_scope=run_scope)

        if expected:
            assert result.ok is True
            assert result.denied is False
        else:
            # Requirement 9.4: a disabled tool is denied.
            assert result.ok is False
            assert result.denied is True
            expected_denials += 1

    # Requirement 9.4: each denial is recorded in the run event history,
    # attributed to the run. Read back the *persisted* history.
    denial_events = [
        event
        for event in router.history(run_id)
        if event.type == WorkflowEventType.TOOL_DENIED
    ]
    assert len(denial_events) == expected_denials
    for event in denial_events:
        assert event.run_id == run_id
        assert event.payload.get("tool") in {f"tool_{t}" for t in _TOOLSET_NAMES}


@settings(
    max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow]
)
@given(
    run_value=st.sampled_from([True, False]),
    toolset=st.sampled_from(_TOOLSET_NAMES),
)
def test_agent_disable_always_beats_run_enable(
    run_value: bool, toolset: str, tmp_path_factory
) -> None:
    """Focused check of Requirement 9.3: with the agent map disabling a toolset,
    no run-level value can re-enable it, and the invocation is denied + recorded."""
    base: Path = tmp_path_factory.mktemp("agent-precedence")
    registry, router, _ = _fresh_registry(base)
    run_id = f"run-{uuid.uuid4().hex}"
    run_scope = RunScope(run_id=run_id, definition_id="def-1")

    scope = ToolScope(
        agent_enabled={toolset: False},
        run_enabled={toolset: run_value},
    )
    tool_name = f"tool_{toolset}"

    # Agent-level disable wins regardless of the run-level value.
    assert registry.is_enabled(tool_name, scope) is False

    result = registry.invoke(tool_name, {}, scope, run_scope=run_scope)
    assert result.ok is False
    assert result.denied is True

    denial_events = [
        event
        for event in router.history(run_id)
        if event.type == WorkflowEventType.TOOL_DENIED
    ]
    assert len(denial_events) == 1
    assert denial_events[0].payload.get("tool") == tool_name
