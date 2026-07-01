"""MCP_Client — connect to MCP servers and expose their tools.

The MCP_Client is the Control_Plane subsystem that connects to external Model
Context Protocol (MCP) tool servers and surfaces their tools through the
:class:`~core.tool_registry.ToolRegistry` with per-server filtering. It owns
five responsibilities, each mapped to an acceptance criterion of Requirement
18:

* **Connect and register (Requirement 18.1).** :meth:`MCPClient.connect`
  connects to a server over its configured transport and registers the
  server's advertised tools into the Tool_Registry, grouped under a
  per-server toolset (``mcp:{server_id}``).
* **Per-server tool filter (Requirement 18.2).** When a tool filter is
  configured the client registers only the tools the filter permits — the
  registered set is exactly ``advertised ∩ filter``.
* **Disconnect handling (Requirement 18.3).** When a server is unreachable
  (either at connect time or via an explicit :meth:`MCPClient.disconnect`) the
  client marks that server's registered tools *unavailable* in the Tool_Registry
  and records the disconnection in the run event history.
* **Grant-only credentials (Requirement 18.4).** Any server credentials are
  obtained exclusively through a Kernel secret grant
  (:class:`~core.orchestration_types.GrantContext`, a grant id + session ref
  reference). Raw secret values never enter Control_Plane state.
* **No raw-secret fallback (Requirement 18.5).** If a server requires
  credentials but no Kernel grant can be issued, the connection is allowed to
  fail — there is no fallback to a raw Control_Plane secret value.

Transport is injected so tests can mock the server. The client depends only on
two small structural interfaces, :class:`MCPTransport` (opens a connection) and
:class:`MCPConnection` (lists/calls tools and closes), keeping it free of any
concrete network or process transport.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from core.database import DatabaseBackend
from core.event_router import EventRouter, WorkflowEventType
from core.helpers import now_iso, to_json
from core.orchestration_types import GrantContext, ToolSpec
from core.tool_registry import ToolRegistry

LOGGER = logging.getLogger("vloop.control_plane.mcp_client")

# Persisted ``mcp_servers.status`` values.
STATUS_CONNECTED = "connected"
STATUS_DISCONNECTED = "disconnected"
STATUS_FAILED = "failed"


class MCPConnectionError(RuntimeError):
    """Raised when an MCP server connection cannot be established.

    Used both when a required credential grant cannot be obtained (no
    raw-secret fallback, Requirement 18.5) and when the transport reports the
    server is unreachable (Requirement 18.3).
    """


@dataclass(frozen=True, slots=True)
class MCPToolDescriptor:
    """A tool advertised by an MCP server.

    Mirrors the MCP tool advertisement shape the client needs to build a
    :class:`~core.orchestration_types.ToolSpec`. ``mutating`` flags a tool that
    performs filesystem mutation or command execution so the Tool_Registry
    routes its execution through a Kernel-managed Sandbox (Requirement 9.5).
    """

    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    mutating: bool = False


@dataclass(slots=True)
class MCPServerConfig:
    """A user-configured MCP server connection.

    Mirrors the ``mcp_servers`` table (``id``, ``name``, ``transport``,
    ``tool_filter_json``, ``grant_ref``). ``tool_filter`` of ``None`` means *no
    filter* (every advertised tool is eligible); an empty collection means *no
    tool is permitted*. ``secret_ref`` names the Kernel secret a credentialed
    server needs; when set, a grant is requested before connecting and the
    connection fails if no grant can be issued (Requirements 18.4, 18.5).
    """

    id: str
    name: str
    transport: str
    tool_filter: Sequence[str] | None = None
    secret_ref: str | None = None
    grant_target: str | None = None

    def filter_set(self) -> set[str] | None:
        """Return the filter as a set, or ``None`` when unfiltered."""
        if self.tool_filter is None:
            return None
        return set(self.tool_filter)


class MCPConnection(Protocol):
    """An open connection to a single MCP server (structurally typed)."""

    def list_tools(self) -> Sequence[MCPToolDescriptor]:
        """Return the tools the server advertises."""
        ...

    def call_tool(self, name: str, args: Mapping[str, Any]) -> Any:
        """Invoke an advertised tool on the server and return its output."""
        ...

    def close(self) -> None:
        """Close the connection, releasing any transport resources."""
        ...


class MCPTransport(Protocol):
    """Opens connections to MCP servers (structurally typed).

    Injected so tests can supply a mock server. ``grant`` is the Kernel secret
    grant obtained for a credentialed server, or ``None`` for an
    unauthenticated one; the transport uses the granted session reference and
    never a raw secret value (Requirement 18.4).
    """

    def connect(
        self, config: MCPServerConfig, grant: GrantContext | None
    ) -> MCPConnection:
        """Open a connection to ``config``'s server, or raise if unreachable."""
        ...


class SecretGrantProvider(Protocol):
    """Issues Kernel secret grants (subset of ``RustInfraExecutionManager``).

    Structurally satisfied by
    :class:`adapters.rust_infra.RustInfraExecutionManager`. Kept narrow so the
    MCP_Client depends only on grant issuance and has no access to raw secrets.
    """

    def request_secret_grant(self, secret_ref: str, target: str) -> GrantContext:
        """Return a :class:`GrantContext` for ``secret_ref`` or raise."""
        ...


class MCPClient:
    """Connects to MCP servers and registers their tools with the registry."""

    def __init__(
        self,
        transport: MCPTransport,
        tool_registry: ToolRegistry,
        *,
        grant_provider: SecretGrantProvider | None = None,
        state: DatabaseBackend | None = None,
        event_router: EventRouter | None = None,
    ) -> None:
        if transport is None:
            raise ValueError("an MCP transport is required")
        if tool_registry is None:
            raise ValueError("a tool registry is required")
        self._transport = transport
        self._registry = tool_registry
        self._grant_provider = grant_provider
        self._state = state
        self._event_router = event_router
        # Live connections and the registry tool names registered per server,
        # so a later disconnect can mark exactly those tools unavailable.
        self._connections: dict[str, MCPConnection] = {}
        self._registered: dict[str, list[str]] = {}

    # -- public API ---------------------------------------------------------

    @staticmethod
    def toolset_id(server_id: str) -> str:
        """Return the per-server toolset id used to group a server's tools."""
        return f"mcp:{server_id}"

    def registered_tool_names(self, server_id: str) -> list[str]:
        """Return the tool names currently registered for ``server_id``."""
        return list(self._registered.get(server_id, ()))

    def connect(
        self, config: MCPServerConfig, *, run_id: str | None = None
    ) -> list[ToolSpec]:
        """Connect to a server and register its filtered tools (Req 18.1, 18.2).

        Obtains a Kernel secret grant first when the server is credentialed; if
        no grant can be issued the connection fails with no raw-secret fallback
        (Requirements 18.4, 18.5). When the transport reports the server is
        unreachable the failure is recorded and any previously registered tools
        for the server are marked unavailable (Requirement 18.3). On success the
        registered :class:`ToolSpec` list (``advertised ∩ filter``) is returned.
        """
        grant = self._obtain_grant(config, run_id=run_id)

        try:
            connection = self._transport.connect(config, grant)
        except MCPConnectionError:
            self._handle_unreachable(config, run_id=run_id)
            raise
        except Exception as exc:  # noqa: BLE001 - normalized to a connection error
            self._handle_unreachable(config, run_id=run_id)
            raise MCPConnectionError(
                f"MCP server {config.id!r} is unreachable: {exc}"
            ) from exc

        try:
            advertised = list(connection.list_tools())
        except Exception as exc:  # noqa: BLE001 - treated as unreachable
            self._safe_close(connection)
            self._handle_unreachable(config, run_id=run_id)
            raise MCPConnectionError(
                f"MCP server {config.id!r} failed to advertise its tools: {exc}"
            ) from exc

        specs = self._register_tools(config, connection, advertised)
        self._connections[config.id] = connection
        self._registered[config.id] = [spec.name for spec in specs]
        self._persist_status(config, STATUS_CONNECTED)
        self._record_event(
            run_id,
            WorkflowEventType.MCP_CONNECTED,
            f"connected to MCP server {config.name!r} ({len(specs)} tool(s) registered)",
            server_id=config.id,
            extra={"tools": [spec.name for spec in specs]},
        )
        return specs

    def disconnect(
        self,
        server_id: str,
        *,
        run_id: str | None = None,
        reason: str = "server unreachable",
    ) -> None:
        """Mark a server's tools unavailable and record the disconnection.

        Implements Requirement 18.3: every tool the client registered for
        ``server_id`` is marked unavailable in the Tool_Registry (it stays
        catalogued so it can be restored on reconnect), the live connection is
        closed best-effort, the persisted server status becomes
        ``disconnected``, and the disconnection is recorded in the run event
        history. Disconnecting an unknown server is a no-op.
        """
        registered = self._registered.get(server_id)
        if registered is None:
            return
        for tool_name in registered:
            self._registry.set_tool_available(tool_name, False)
        connection = self._connections.pop(server_id, None)
        if connection is not None:
            self._safe_close(connection)
        self._persist_status_by_id(server_id, STATUS_DISCONNECTED)
        self._record_event(
            run_id,
            WorkflowEventType.MCP_DISCONNECTED,
            f"MCP server {server_id!r} disconnected: {reason}",
            server_id=server_id,
            extra={"reason": reason, "tools": list(registered)},
        )

    # -- internals ----------------------------------------------------------

    def _obtain_grant(
        self, config: MCPServerConfig, *, run_id: str | None
    ) -> GrantContext | None:
        """Obtain a Kernel grant for a credentialed server (Req 18.4, 18.5).

        Returns ``None`` for an unauthenticated server. For a credentialed
        server, a grant is requested through the injected provider; if no
        provider is configured or the grant cannot be issued the connection is
        failed rather than falling back to a raw secret value (Requirement 18.5).
        """
        if not config.secret_ref:
            return None

        if self._grant_provider is None:
            self._persist_status(config, STATUS_FAILED)
            self._record_event(
                run_id,
                WorkflowEventType.MCP_DISCONNECTED,
                f"MCP server {config.id!r} requires credentials but no kernel "
                "grant source is available; connection failed with no "
                "raw-secret fallback",
                server_id=config.id,
            )
            raise MCPConnectionError(
                f"MCP server {config.id!r} requires credentials but no kernel "
                "secret grant source is configured; refusing to fall back to a "
                "raw Control_Plane secret"
            )

        target = config.grant_target or self.toolset_id(config.id)
        try:
            grant = self._grant_provider.request_secret_grant(
                config.secret_ref, target
            )
        except Exception as exc:  # noqa: BLE001 - normalized to a connection error
            self._persist_status(config, STATUS_FAILED)
            self._record_event(
                run_id,
                WorkflowEventType.MCP_DISCONNECTED,
                f"MCP server {config.id!r} credential grant failed; connection "
                "failed with no raw-secret fallback",
                server_id=config.id,
            )
            raise MCPConnectionError(
                f"could not obtain a kernel secret grant for MCP server "
                f"{config.id!r}; refusing to fall back to a raw Control_Plane "
                "secret"
            ) from exc

        if grant is None:  # defensive: a provider must return a grant or raise
            self._persist_status(config, STATUS_FAILED)
            raise MCPConnectionError(
                f"no kernel secret grant was issued for MCP server {config.id!r}; "
                "refusing to fall back to a raw Control_Plane secret"
            )
        return grant

    def _register_tools(
        self,
        config: MCPServerConfig,
        connection: MCPConnection,
        advertised: Iterable[MCPToolDescriptor],
    ) -> list[ToolSpec]:
        """Register ``advertised ∩ filter`` into the registry (Req 18.1, 18.2)."""
        allowed = config.filter_set()
        toolset = self.toolset_id(config.id)
        specs: list[ToolSpec] = []
        for descriptor in advertised:
            if allowed is not None and descriptor.name not in allowed:
                continue
            spec = ToolSpec(
                name=descriptor.name,
                description=descriptor.description,
                toolset=toolset,
                input_schema=dict(descriptor.input_schema),
                mutating=descriptor.mutating,
            )
            self._registry.register_tool(
                spec, handler=self._make_handler(connection, descriptor.name)
            )
            # register_tool clears any prior unavailable mark; be explicit so a
            # reconnect restores availability (Requirement 18.3).
            self._registry.set_tool_available(spec.name, True)
            specs.append(spec)
        return specs

    @staticmethod
    def _make_handler(connection: MCPConnection, tool_name: str):
        """Build an in-process handler that proxies invocations to the server."""

        def _handler(args: dict[str, Any]) -> Any:
            return connection.call_tool(tool_name, args or {})

        return _handler

    def _handle_unreachable(
        self, config: MCPServerConfig, *, run_id: str | None
    ) -> None:
        """Mark a server's tools unavailable and record it became unreachable."""
        registered = self._registered.get(config.id, [])
        for tool_name in registered:
            self._registry.set_tool_available(tool_name, False)
        self._connections.pop(config.id, None)
        self._persist_status(config, STATUS_DISCONNECTED)
        self._record_event(
            run_id,
            WorkflowEventType.MCP_DISCONNECTED,
            f"MCP server {config.id!r} is unreachable",
            server_id=config.id,
            extra={"tools": list(registered)},
        )

    @staticmethod
    def _safe_close(connection: MCPConnection) -> None:
        try:
            connection.close()
        except Exception:  # noqa: BLE001 - close is best-effort
            LOGGER.debug("MCP connection close raised; ignoring", exc_info=True)

    # -- persistence + events ----------------------------------------------

    def _persist_status(self, config: MCPServerConfig, status: str) -> None:
        """Upsert the server row with ``status`` (no-op without a backend)."""
        if self._state is None:
            return
        tool_filter_json = (
            to_json(list(config.tool_filter))
            if config.tool_filter is not None
            else None
        )
        now = now_iso()
        existing = self._state.fetch_one(
            "SELECT id FROM mcp_servers WHERE id = ?", (config.id,)
        )
        if existing is None:
            self._state.execute(
                "INSERT INTO mcp_servers "
                "(id, name, transport, tool_filter_json, grant_ref, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    config.id,
                    config.name,
                    config.transport,
                    tool_filter_json,
                    config.secret_ref,
                    status,
                    now,
                ),
            )
        else:
            self._state.execute(
                "UPDATE mcp_servers SET name = ?, transport = ?, "
                "tool_filter_json = ?, grant_ref = ?, status = ? WHERE id = ?",
                (
                    config.name,
                    config.transport,
                    tool_filter_json,
                    config.secret_ref,
                    status,
                    config.id,
                ),
            )

    def _persist_status_by_id(self, server_id: str, status: str) -> None:
        """Update only the status column for a known server id."""
        if self._state is None:
            return
        self._state.execute(
            "UPDATE mcp_servers SET status = ? WHERE id = ?", (status, server_id)
        )

    def _record_event(
        self,
        run_id: str | None,
        event_type: str,
        message: str,
        *,
        server_id: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Record an MCP lifecycle event in the run event history.

        The Event_Router attributes every event to a run (Requirement 21.5), so
        an event is emitted only when the operation carries a ``run_id``. When
        no run context is available the event is logged instead so the
        lifecycle is never lost.
        """
        payload = {"server_id": server_id}
        if extra:
            payload.update(extra)
        if self._event_router is not None and run_id:
            self._event_router.emit(run_id, event_type, message, payload=payload)
        else:
            LOGGER.info("%s (server=%s)", message, server_id)
