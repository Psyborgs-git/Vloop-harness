"""Unit tests for the MCP_Client (`core/mcp_client.py`).

Covers task 28.1: connect over the configured transport and register tools
into the Tool_Registry (Req 18.1); apply per-server tool filters so the
registered set is ``advertised ∩ filter`` (Req 18.2); mark tools unavailable
and record the disconnection when a server is unreachable (Req 18.3); obtain
credentials only via kernel grants (Req 18.4); and fail the connection with no
raw-secret fallback when no grant is available (Req 18.5).

The MCP server transport and the kernel grant provider are mocked so the tests
exercise the client's own logic without any real network or kernel access.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.database import SQLiteBackend
from core.event_router import EventRouter, WorkflowEventType
from core.mcp_client import (
    MCPClient,
    MCPConnectionError,
    MCPServerConfig,
    MCPToolDescriptor,
    STATUS_CONNECTED,
    STATUS_DISCONNECTED,
    STATUS_FAILED,
)
from core.orchestration_types import GrantContext, ToolScope
from core.tool_registry import ToolRegistry


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class FakeConnection:
    """A mock open MCP connection advertising a fixed tool set."""

    def __init__(self, tools: list[MCPToolDescriptor]) -> None:
        self._tools = tools
        self.closed = False
        self.calls: list[tuple[str, dict]] = []

    def list_tools(self):
        return list(self._tools)

    def call_tool(self, name, args):
        self.calls.append((name, dict(args)))
        return {"tool": name, "args": dict(args)}

    def close(self):
        self.closed = True


class FakeTransport:
    """A mock transport that returns a connection or simulates unreachability."""

    def __init__(self, connection: FakeConnection | None, *, unreachable=False):
        self._connection = connection
        self._unreachable = unreachable
        self.connect_calls: list[tuple[MCPServerConfig, GrantContext | None]] = []

    def connect(self, config, grant):
        self.connect_calls.append((config, grant))
        if self._unreachable:
            raise ConnectionError("server unreachable")
        assert self._connection is not None
        return self._connection


class FakeGrantProvider:
    """A mock kernel grant provider."""

    def __init__(self, *, fail=False):
        self._fail = fail
        self.requests: list[tuple[str, str]] = []

    def request_secret_grant(self, secret_ref, target):
        self.requests.append((secret_ref, target))
        if self._fail:
            raise RuntimeError("kernel refused the grant")
        return GrantContext(grant_id="grant-1", session_ref="session-1")


@pytest.fixture()
def backend(tmp_path: Path) -> SQLiteBackend:
    return SQLiteBackend(tmp_path / "mcp-test.db")


def _tools() -> list[MCPToolDescriptor]:
    return [
        MCPToolDescriptor(name="search", description="web search"),
        MCPToolDescriptor(name="write_file", description="write a file", mutating=True),
        MCPToolDescriptor(name="read_file", description="read a file"),
    ]


# ---------------------------------------------------------------------------
# Connect + register (Req 18.1)
# ---------------------------------------------------------------------------


def test_connect_registers_advertised_tools(backend: SQLiteBackend):
    registry = ToolRegistry()
    connection = FakeConnection(_tools())
    client = MCPClient(FakeTransport(connection), registry, state=backend)

    config = MCPServerConfig(id="srv1", name="Tools", transport="stdio")
    specs = client.connect(config)

    names = {spec.name for spec in specs}
    assert names == {"search", "write_file", "read_file"}
    # All registered into the per-server toolset and present in the catalog.
    toolset = MCPClient.toolset_id("srv1")
    for spec in specs:
        assert spec.toolset == toolset
        assert registry.get_tool(spec.name) is not None
        assert registry.is_available(spec.name)
    # The mutating advertisement is preserved so the registry sandbox-routes it.
    assert registry.get_tool("write_file").mutating is True
    # Server status persisted as connected.
    row = backend.fetch_one("SELECT status FROM mcp_servers WHERE id = ?", ("srv1",))
    assert row["status"] == STATUS_CONNECTED


def test_registered_tool_handler_proxies_to_server():
    registry = ToolRegistry()
    connection = FakeConnection([MCPToolDescriptor(name="search")])
    client = MCPClient(FakeTransport(connection), registry)
    config = MCPServerConfig(id="srv1", name="Tools", transport="stdio")
    client.connect(config)

    scope = ToolScope(run_enabled={MCPClient.toolset_id("srv1"): True})
    result = registry.invoke("search", {"q": "vloop"}, scope)

    assert result.ok is True
    assert connection.calls == [("search", {"q": "vloop"})]


# ---------------------------------------------------------------------------
# Per-server filter (Req 18.2) — registered = advertised ∩ filter
# ---------------------------------------------------------------------------


def test_filter_registers_only_permitted_tools():
    registry = ToolRegistry()
    connection = FakeConnection(_tools())
    client = MCPClient(FakeTransport(connection), registry)

    # Filter includes one advertised tool and one that is not advertised.
    config = MCPServerConfig(
        id="srv1", name="Tools", transport="stdio", tool_filter=["search", "ghost"]
    )
    specs = client.connect(config)

    assert {spec.name for spec in specs} == {"search"}
    assert registry.get_tool("write_file") is None
    assert client.registered_tool_names("srv1") == ["search"]


def test_empty_filter_registers_no_tools():
    registry = ToolRegistry()
    connection = FakeConnection(_tools())
    client = MCPClient(FakeTransport(connection), registry)

    config = MCPServerConfig(id="srv1", name="Tools", transport="stdio", tool_filter=[])
    specs = client.connect(config)

    assert specs == []
    assert client.registered_tool_names("srv1") == []


# ---------------------------------------------------------------------------
# Disconnect handling (Req 18.3)
# ---------------------------------------------------------------------------


def test_disconnect_marks_tools_unavailable_and_records_event(backend: SQLiteBackend):
    registry = ToolRegistry()
    router = EventRouter(backend)
    connection = FakeConnection(_tools())
    client = MCPClient(
        FakeTransport(connection), registry, state=backend, event_router=router
    )

    config = MCPServerConfig(id="srv1", name="Tools", transport="stdio")
    client.connect(config, run_id="run-1")

    client.disconnect("srv1", run_id="run-1", reason="connection lost")

    # Tools stay catalogued but are no longer available or enabled.
    for name in ("search", "write_file", "read_file"):
        assert registry.get_tool(name) is not None
        assert registry.is_available(name) is False
    scope = ToolScope(run_enabled={MCPClient.toolset_id("srv1"): True})
    assert registry.is_enabled("search", scope) is False
    assert connection.closed is True

    # Disconnection recorded in the run event history and persisted status.
    history = router.history("run-1")
    assert any(e.type == WorkflowEventType.MCP_DISCONNECTED for e in history)
    row = backend.fetch_one("SELECT status FROM mcp_servers WHERE id = ?", ("srv1",))
    assert row["status"] == STATUS_DISCONNECTED


def test_unreachable_server_records_disconnection_and_raises(backend: SQLiteBackend):
    registry = ToolRegistry()
    router = EventRouter(backend)
    client = MCPClient(
        FakeTransport(None, unreachable=True),
        registry,
        state=backend,
        event_router=router,
    )

    config = MCPServerConfig(id="srv1", name="Tools", transport="stdio")
    with pytest.raises(MCPConnectionError):
        client.connect(config, run_id="run-1")

    history = router.history("run-1")
    assert any(e.type == WorkflowEventType.MCP_DISCONNECTED for e in history)


def test_reconnect_restores_tool_availability():
    registry = ToolRegistry()
    connection = FakeConnection([MCPToolDescriptor(name="search")])
    client = MCPClient(FakeTransport(connection), registry)
    config = MCPServerConfig(id="srv1", name="Tools", transport="stdio")

    client.connect(config)
    client.disconnect("srv1")
    assert registry.is_available("search") is False

    client.connect(config)
    assert registry.is_available("search") is True


# ---------------------------------------------------------------------------
# Grant-only credentials (Req 18.4) and no raw-secret fallback (Req 18.5)
# ---------------------------------------------------------------------------


def test_credentialed_server_obtains_grant_and_passes_it_to_transport():
    registry = ToolRegistry()
    connection = FakeConnection([MCPToolDescriptor(name="search")])
    transport = FakeTransport(connection)
    grants = FakeGrantProvider()
    client = MCPClient(transport, registry, grant_provider=grants)

    config = MCPServerConfig(
        id="srv1",
        name="Tools",
        transport="stdio",
        secret_ref="mcp/srv1/token",
        grant_target="mcp:srv1",
    )
    client.connect(config)

    # The grant was requested and handed to the transport — not a raw secret.
    assert grants.requests == [("mcp/srv1/token", "mcp:srv1")]
    _, grant = transport.connect_calls[0]
    assert isinstance(grant, GrantContext)
    assert grant.grant_id == "grant-1"


def test_missing_grant_source_fails_with_no_raw_fallback(backend: SQLiteBackend):
    registry = ToolRegistry()
    # Credentialed server but NO grant provider configured.
    client = MCPClient(FakeTransport(None), registry, state=backend)

    config = MCPServerConfig(
        id="srv1", name="Tools", transport="stdio", secret_ref="mcp/srv1/token"
    )
    with pytest.raises(MCPConnectionError):
        client.connect(config)

    row = backend.fetch_one("SELECT status FROM mcp_servers WHERE id = ?", ("srv1",))
    assert row["status"] == STATUS_FAILED


def test_failed_grant_fails_connection_with_no_raw_fallback():
    registry = ToolRegistry()
    transport = FakeTransport(FakeConnection([]))
    grants = FakeGrantProvider(fail=True)
    client = MCPClient(transport, registry, grant_provider=grants)

    config = MCPServerConfig(
        id="srv1", name="Tools", transport="stdio", secret_ref="mcp/srv1/token"
    )
    with pytest.raises(MCPConnectionError):
        client.connect(config)

    # The transport was never reached because the grant could not be issued.
    assert transport.connect_calls == []
