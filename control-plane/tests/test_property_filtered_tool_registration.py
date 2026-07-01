"""Property-based test for MCP per-server filtered tool registration.

# Feature: orchestration-engine-completion, Property 41: MCP tool registration honors the per-server filter

Property 41 states that *for any* set of tools advertised by an MCP server and
any per-server filter, the tools registered into the Tool_Registry equal the
intersection of the advertised tools and the filter (Requirement 18.2).

This test drives :meth:`core.mcp_client.MCPClient.connect` over a randomly
generated set of advertised tools and a randomly generated per-server filter.
The filter is deliberately drawn to exercise the full space of relationships
with the advertised set — a subset, a superset, a disjoint set, an overlapping
mix, the empty set, and the unfiltered ``None`` case. It asserts:

* when a filter is configured, the registered tool names equal exactly the
  intersection ``advertised ∩ filter``;
* when the filter is ``None`` (unfiltered), every advertised tool is
  registered; and
* filter entries that are not advertised are ignored (they never appear in the
  registered set).

**Validates: Requirements 18.2**
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from core.mcp_client import MCPClient, MCPServerConfig, MCPToolDescriptor
from core.tool_registry import ToolRegistry


# ---------------------------------------------------------------------------
# Test doubles (mirrors tests/test_mcp_client.py patterns)
# ---------------------------------------------------------------------------


class FakeConnection:
    """A mock open MCP connection advertising a fixed tool set."""

    def __init__(self, tools: list[MCPToolDescriptor]) -> None:
        self._tools = tools

    def list_tools(self):
        return list(self._tools)

    def call_tool(self, name, args):  # pragma: no cover - not exercised here
        return {"tool": name, "args": dict(args)}

    def close(self):  # pragma: no cover - not exercised here
        pass


class FakeTransport:
    """A mock transport returning a fixed connection."""

    def __init__(self, connection: FakeConnection) -> None:
        self._connection = connection

    def connect(self, config, grant):
        return self._connection


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Tool-name-like tokens. A small alphabet keeps the chance of overlap between
# the advertised set and the filter high, so the intersection case is well
# exercised alongside the disjoint case.
_tool_names = st.text(
    alphabet="abcde",
    min_size=1,
    max_size=4,
)

# A random set of advertised tool names (deduplicated to a set, as a server
# advertises each tool once).
_advertised_names = st.lists(_tool_names, max_size=8, unique=True)

# A random filter expressed as a list of names, or ``None`` meaning unfiltered.
# Allowing arbitrary names (not just advertised ones) exercises subset,
# superset, disjoint, overlapping, and empty filters.
_filters = st.one_of(
    st.none(),
    st.lists(_tool_names, max_size=8, unique=True),
)


# ---------------------------------------------------------------------------
# Property 41: MCP tool registration honors the per-server filter
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(advertised_names=_advertised_names, tool_filter=_filters)
def test_registered_tools_equal_advertised_intersect_filter(
    advertised_names: list[str],
    tool_filter: list[str] | None,
) -> None:
    """Registered tools equal ``advertised ∩ filter`` (or all advertised when
    the filter is ``None``); filter entries not advertised are ignored."""
    advertised = [MCPToolDescriptor(name=name) for name in advertised_names]
    registry = ToolRegistry()
    client = MCPClient(FakeTransport(FakeConnection(advertised)), registry)

    config = MCPServerConfig(
        id="srv1",
        name="Tools",
        transport="stdio",
        tool_filter=tool_filter,
    )
    specs = client.connect(config)

    registered = set(client.registered_tool_names("srv1"))
    # The returned specs and the recorded registered names must agree.
    assert registered == {spec.name for spec in specs}

    advertised_set = set(advertised_names)
    if tool_filter is None:
        # Unfiltered: every advertised tool is registered.
        assert registered == advertised_set
    else:
        # Filtered: exactly the intersection of advertised and filter.
        expected = advertised_set & set(tool_filter)
        assert registered == expected
        # Filter entries that are not advertised are ignored.
        not_advertised = set(tool_filter) - advertised_set
        assert registered.isdisjoint(not_advertised)
