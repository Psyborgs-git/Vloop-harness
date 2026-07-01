"""Integration tests for the MCP connection lifecycle (task 28.3).

These exercise the *full* MCP_Client lifecycle end to end rather than the
client's internals in isolation: a real :class:`~core.tool_registry.ToolRegistry`,
a real :class:`~core.event_router.EventRouter` backed by a temporary SQLite
database, and a real :class:`~core.mcp_client.MCPClient` are wired together. Only
the external MCP server is mocked, through an injected transport — exactly the
seam the production code exposes for swapping in a real stdio/HTTP transport.

Scenarios:

* **Connect + register (Req 18.1).** Connecting over the configured transport
  registers the server's advertised tools into the Tool_Registry, the tools are
  actually invokable through the registry (the call is proxied to the server),
  the persisted server status is ``connected``, and the connection is recorded
  in the run event history that survives in SQLite.
* **Disconnect / unreachable (Req 18.3).** An explicit disconnect, and a server
  that becomes unreachable on a later reconnect attempt, both mark the server's
  registered tools *unavailable* in the Tool_Registry (so invocation is denied)
  and record the disconnection in the event history with status ``disconnected``.
* **No raw-secret fallback (Req 18.5).** A credentialed server whose credential
  grant cannot be issued (no grant source, or a failing grant source) fails the
  connection with :class:`MCPConnectionError`, persists status ``failed``, and
  never reaches the transport — there is no fallback to a raw secret value.
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
from core.orchestration_types import GrantContext, RunScope, ToolScope
from core.tool_registry import ToolRegistry


# ---------------------------------------------------------------------------
# Mock MCP server (the only mocked seam; everything else is the real subsystem)
# ---------------------------------------------------------------------------


class MockMCPConnection:
    """A mock open connection to a single MCP server.

    Advertises a fixed tool set and echoes invocations back so a test can prove
    a registered tool's invocation is actually proxied to the server.
    """

    def __init__(self, tools: list[MCPToolDescriptor]) -> None:
        self._tools = tools
        self.closed = False
        self.calls: list[tuple[str, dict]] = []

    def list_tools(self) -> list[MCPToolDescriptor]:
        return list(self._tools)

    def call_tool(self, name: str, args: dict):
        self.calls.append((name, dict(args)))
        return {"server_tool": name, "echo": dict(args)}

    def close(self) -> None:
        self.closed = True


class MockMCPTransport:
    """A mock transport whose reachability can be toggled between connects.

    Captures every ``(config, grant)`` pair it is asked to connect with so a
    test can assert the transport only ever receives a :class:`GrantContext`
    reference (never a raw secret) and that it is not reached at all when a
    required grant cannot be issued.
    """

    def __init__(self, connection: MockMCPConnection) -> None:
        self._connection = connection
        self.reachable = True
        self.connect_calls: list[tuple[MCPServerConfig, GrantContext | None]] = []

    def connect(self, config: MCPServerConfig, grant: GrantContext | None):
        self.connect_calls.append((config, grant))
        if not self.reachable:
            raise ConnectionError(f"MCP server {config.id!r} is unreachable")
        return self._connection


class MockGrantProvider:
    """A mock Kernel secret-grant provider.

    Issues a grant *reference* (id + session ref) or, when ``fail`` is set,
    refuses — modelling the Kernel declining to mint a grant. It never returns
    a raw secret value, mirroring the real grant-only contract.
    """

    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail
        self.requests: list[tuple[str, str]] = []

    def request_secret_grant(self, secret_ref: str, target: str) -> GrantContext:
        self.requests.append((secret_ref, target))
        if self._fail:
            raise RuntimeError("kernel declined to issue a secret grant")
        return GrantContext(grant_id="grant-xyz", session_ref="session-xyz")


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def backend(tmp_path: Path) -> SQLiteBackend:
    """A temporary SQLite backend (auto-creates the schema)."""
    return SQLiteBackend(tmp_path / "mcp-lifecycle.db")


def _advertised_tools() -> list[MCPToolDescriptor]:
    return [
        MCPToolDescriptor(name="search", description="web search"),
        MCPToolDescriptor(name="fetch_doc", description="fetch a document"),
    ]


# ---------------------------------------------------------------------------
# (1) Connect + tool registration, tools invokable, status connected (Req 18.1)
# ---------------------------------------------------------------------------


def test_lifecycle_connect_registers_invokable_tools_and_records_event(
    backend: SQLiteBackend,
):
    registry = ToolRegistry()
    router = EventRouter(backend)
    connection = MockMCPConnection(_advertised_tools())
    transport = MockMCPTransport(connection)
    client = MCPClient(
        transport, registry, state=backend, event_router=router
    )

    config = MCPServerConfig(id="srv-docs", name="Docs Server", transport="stdio")
    specs = client.connect(config, run_id="run-1")

    # Tools advertised by the server are registered into the per-server toolset.
    toolset = MCPClient.toolset_id("srv-docs")
    assert {s.name for s in specs} == {"search", "fetch_doc"}
    for spec in specs:
        assert spec.toolset == toolset
        assert registry.get_tool(spec.name) is not None
        assert registry.is_available(spec.name) is True

    # The registered tools are actually invokable through the real registry and
    # the invocation is proxied to the mocked server.
    scope = ToolScope(run_enabled={toolset: True})
    run_scope = RunScope(run_id="run-1", definition_id="def-1")
    result = registry.invoke("search", {"q": "vloop"}, scope, run_scope=run_scope)
    assert result.ok is True
    assert result.output == {"server_tool": "search", "echo": {"q": "vloop"}}
    assert connection.calls == [("search", {"q": "vloop"})]

    # Persisted server status is connected.
    row = backend.fetch_one(
        "SELECT status FROM mcp_servers WHERE id = ?", ("srv-docs",)
    )
    assert row["status"] == STATUS_CONNECTED

    # The connection is recorded in the run event history (survives in SQLite).
    history = router.history("run-1")
    connected = [e for e in history if e.type == WorkflowEventType.MCP_CONNECTED]
    assert len(connected) == 1
    assert connected[0].payload["server_id"] == "srv-docs"
    assert set(connected[0].payload["tools"]) == {"search", "fetch_doc"}


# ---------------------------------------------------------------------------
# (2) Disconnect / unreachable marks tools unavailable, status disconnected (18.3)
# ---------------------------------------------------------------------------


def test_lifecycle_disconnect_marks_tools_unavailable_and_records_event(
    backend: SQLiteBackend,
):
    registry = ToolRegistry()
    router = EventRouter(backend)
    connection = MockMCPConnection(_advertised_tools())
    transport = MockMCPTransport(connection)
    client = MCPClient(
        transport, registry, state=backend, event_router=router
    )

    config = MCPServerConfig(id="srv-docs", name="Docs Server", transport="stdio")
    client.connect(config, run_id="run-1")

    client.disconnect("srv-docs", run_id="run-1", reason="connection lost")

    toolset = MCPClient.toolset_id("srv-docs")
    scope = ToolScope(run_enabled={toolset: True})
    run_scope = RunScope(run_id="run-1", definition_id="def-1")

    # Tools stay catalogued but are unavailable, so invocation is denied.
    for name in ("search", "fetch_doc"):
        assert registry.get_tool(name) is not None
        assert registry.is_available(name) is False
    denied = registry.invoke("search", {"q": "x"}, scope, run_scope=run_scope)
    assert denied.ok is False
    assert denied.denied is True
    assert connection.closed is True

    # Persisted status disconnected, disconnection recorded in event history.
    row = backend.fetch_one(
        "SELECT status FROM mcp_servers WHERE id = ?", ("srv-docs",)
    )
    assert row["status"] == STATUS_DISCONNECTED
    history = router.history("run-1")
    assert any(e.type == WorkflowEventType.MCP_DISCONNECTED for e in history)


def test_lifecycle_unreachable_on_reconnect_marks_tools_unavailable(
    backend: SQLiteBackend,
):
    registry = ToolRegistry()
    router = EventRouter(backend)
    connection = MockMCPConnection(_advertised_tools())
    transport = MockMCPTransport(connection)
    client = MCPClient(
        transport, registry, state=backend, event_router=router
    )
    config = MCPServerConfig(id="srv-docs", name="Docs Server", transport="stdio")

    # Successful connect, then the server goes away before a reconnect attempt.
    client.connect(config, run_id="run-1")
    toolset = MCPClient.toolset_id("srv-docs")
    assert registry.is_available("search") is True

    transport.reachable = False
    with pytest.raises(MCPConnectionError):
        client.connect(config, run_id="run-1")

    # The previously registered tools are now unavailable and invocation denied.
    for name in ("search", "fetch_doc"):
        assert registry.is_available(name) is False
    scope = ToolScope(run_enabled={toolset: True})
    run_scope = RunScope(run_id="run-1", definition_id="def-1")
    assert registry.invoke("search", {}, scope, run_scope=run_scope).denied is True

    # Status disconnected and the disconnection is in the event history.
    row = backend.fetch_one(
        "SELECT status FROM mcp_servers WHERE id = ?", ("srv-docs",)
    )
    assert row["status"] == STATUS_DISCONNECTED
    history = router.history("run-1")
    assert any(e.type == WorkflowEventType.MCP_DISCONNECTED for e in history)


# ---------------------------------------------------------------------------
# (3) No grant -> connection fails, status failed, no raw-secret fallback (18.5)
# ---------------------------------------------------------------------------


def test_lifecycle_no_grant_source_fails_without_raw_secret_fallback(
    backend: SQLiteBackend,
):
    registry = ToolRegistry()
    router = EventRouter(backend)
    connection = MockMCPConnection(_advertised_tools())
    transport = MockMCPTransport(connection)
    # Credentialed server but NO grant provider configured at all.
    client = MCPClient(
        transport, registry, state=backend, event_router=router
    )

    config = MCPServerConfig(
        id="srv-secure",
        name="Secure Server",
        transport="stdio",
        secret_ref="mcp/srv-secure/token",
    )
    with pytest.raises(MCPConnectionError):
        client.connect(config, run_id="run-1")

    # The transport was never reached — no raw-secret fallback path was taken.
    assert transport.connect_calls == []
    # No tools were registered, and the status is failed.
    assert client.registered_tool_names("srv-secure") == []
    row = backend.fetch_one(
        "SELECT status FROM mcp_servers WHERE id = ?", ("srv-secure",)
    )
    assert row["status"] == STATUS_FAILED


def test_lifecycle_failed_grant_fails_without_raw_secret_fallback(
    backend: SQLiteBackend,
):
    registry = ToolRegistry()
    router = EventRouter(backend)
    connection = MockMCPConnection(_advertised_tools())
    transport = MockMCPTransport(connection)
    grants = MockGrantProvider(fail=True)
    client = MCPClient(
        transport,
        registry,
        grant_provider=grants,
        state=backend,
        event_router=router,
    )

    config = MCPServerConfig(
        id="srv-secure",
        name="Secure Server",
        transport="stdio",
        secret_ref="mcp/srv-secure/token",
        grant_target="mcp:srv-secure",
    )
    with pytest.raises(MCPConnectionError):
        client.connect(config, run_id="run-1")

    # A grant was attempted, it failed, and the transport was never reached.
    assert grants.requests == [("mcp/srv-secure/token", "mcp:srv-secure")]
    assert transport.connect_calls == []
    row = backend.fetch_one(
        "SELECT status FROM mcp_servers WHERE id = ?", ("srv-secure",)
    )
    assert row["status"] == STATUS_FAILED


def test_lifecycle_credentialed_connect_passes_grant_reference_not_raw_secret(
    backend: SQLiteBackend,
):
    registry = ToolRegistry()
    router = EventRouter(backend)
    connection = MockMCPConnection(_advertised_tools())
    transport = MockMCPTransport(connection)
    grants = MockGrantProvider()
    client = MCPClient(
        transport,
        registry,
        grant_provider=grants,
        state=backend,
        event_router=router,
    )

    config = MCPServerConfig(
        id="srv-secure",
        name="Secure Server",
        transport="stdio",
        secret_ref="mcp/srv-secure/token",
        grant_target="mcp:srv-secure",
    )
    client.connect(config, run_id="run-1")

    # The transport received a grant *reference* (id + session ref), never a
    # raw secret value, confirming the grant-only credential path (Req 18.4/18.5).
    assert len(transport.connect_calls) == 1
    _, grant = transport.connect_calls[0]
    assert isinstance(grant, GrantContext)
    assert grant.grant_id == "grant-xyz"
    assert grant.session_ref == "session-xyz"
    row = backend.fetch_one(
        "SELECT status FROM mcp_servers WHERE id = ?", ("srv-secure",)
    )
    assert row["status"] == STATUS_CONNECTED
