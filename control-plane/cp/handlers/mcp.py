"""MCP server routes: configure, list, inspect, connect, and remove MCP servers.

Exposes the Control_Plane API over the MCP_Client (`core/mcp_client.py`), which
connects to external Model Context Protocol tool servers and surfaces their
tools through the Tool_Registry with per-server filtering (Requirement 18).

Routes are mounted under ``/api/v1/mcp/servers``:

* ``GET    /api/v1/mcp/servers``                  — list configured MCP server
  connections (Requirement 18.1).
* ``POST   /api/v1/mcp/servers``                  — configure (create) an MCP
  server connection (Requirement 18.1).
* ``GET    /api/v1/mcp/servers/{id}``             — inspect a single configured
  server connection.
* ``PUT|PATCH|POST /api/v1/mcp/servers/{id}``     — re-configure (update) a
  server connection.
* ``DELETE /api/v1/mcp/servers/{id}``             — remove a server connection.
* ``POST   /api/v1/mcp/servers/{id}/connect``     — connect to the server and
  register its (filtered) tools in the Tool_Registry (Requirement 18.1, 18.2).
* ``POST   /api/v1/mcp/servers/{id}/disconnect``  — disconnect, marking the
  server's tools unavailable (Requirement 18.3).

Following the handler conventions in ``cp/handlers/agents.py`` and
``cp/handlers/schedules.py``, each handler receives
``(handler, method, path, query, body, runtime)`` and writes its response via
``write_json``. The MCP_Client is reached only through documented runtime
accessors; this module never touches the client directly.

Runtime accessor contract (real wiring is deferred to task 30.10):

* ``runtime.list_mcp_servers() -> list[dict]``
      Return all configured MCP server connections (id, name, transport,
      tool_filter, status, …) for Requirement 18.1.
* ``runtime.configure_mcp_server(config: dict) -> dict``
      Create or update a server connection from the request body and return the
      stored representation. Invalid configuration raises ``ValueError`` (→ 400).
* ``runtime.get_mcp_server(server_id: str) -> dict``
      Return a single configured server, or raise ``KeyError`` (→ 404) when the
      server id is unknown.
* ``runtime.remove_mcp_server(server_id: str) -> None``
      Remove a configured server connection; raises ``KeyError`` (→ 404) when
      the server id is unknown.
* ``runtime.connect_mcp_server(server_id: str) -> dict``
      Connect to the server and register its filtered tools, returning the
      server's connection state. Raises ``KeyError`` (→ 404) for an unknown id;
      a connection failure surfaces as the MCP_Client's connection error.
* ``runtime.disconnect_mcp_server(server_id: str) -> dict``
      Disconnect the server, marking its tools unavailable (Requirement 18.3),
      and return the server's connection state. Raises ``KeyError`` (→ 404) for
      an unknown id.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any
from urllib.parse import unquote

from cp.handlers.router import register
from cp.http_responders import write_json
from cp.http_utils import require_method, split_segments

# ---------------------------------------------------------------------------
# Collection  /api/v1/mcp/servers
# ---------------------------------------------------------------------------


def _handle_servers(
    handler: Any, method: str, _path: str, _query: Any, body: Any, runtime: Any
) -> None:
    """GET lists configured servers; POST configures one (Requirement 18.1)."""
    if method == "GET":
        write_json(handler, {"mcpServers": runtime.list_mcp_servers()})
    elif method == "POST":
        server = runtime.configure_mcp_server(body)
        write_json(handler, {"mcpServer": server}, status=HTTPStatus.CREATED)
    else:
        require_method(method, {"GET", "POST"})


# ---------------------------------------------------------------------------
# Singleton  /api/v1/mcp/servers/{id}
# ---------------------------------------------------------------------------


def _handle_server(
    handler: Any, method: str, _path: str, _query: Any, body: Any, runtime: Any
) -> None:
    segments = split_segments(_path)
    server_id = unquote(segments[4])

    if method == "GET":
        server = runtime.get_mcp_server(server_id)
        if server is None:
            raise KeyError(f"MCP server `{server_id}` was not found")
        write_json(handler, {"mcpServer": server})
    elif method in {"PUT", "PATCH", "POST"}:
        # Re-configure an existing connection; pin the id from the path so the
        # body cannot retarget a different server.
        config = dict(body or {})
        config["id"] = server_id
        server = runtime.configure_mcp_server(config)
        write_json(handler, {"mcpServer": server})
    elif method == "DELETE":
        runtime.remove_mcp_server(server_id)
        write_json(handler, {"ok": True, "mcpServerId": server_id})
    else:
        require_method(method, {"GET", "PUT", "PATCH", "POST", "DELETE"})


# ---------------------------------------------------------------------------
# Sub-resources  /api/v1/mcp/servers/{id}/{action}
# ---------------------------------------------------------------------------


def _handle_server_action(
    handler: Any, method: str, _path: str, _query: Any, _body: Any, runtime: Any
) -> None:
    """POST /{id}/connect and POST /{id}/disconnect (Requirements 18.1, 18.3)."""
    segments = split_segments(_path)
    server_id = unquote(segments[4])
    suffix = segments[5]

    if suffix == "connect":
        require_method(method, {"POST"})
        server = runtime.connect_mcp_server(server_id)
        write_json(handler, {"mcpServer": server})
    elif suffix == "disconnect":
        require_method(method, {"POST"})
        server = runtime.disconnect_mcp_server(server_id)
        write_json(handler, {"mcpServer": server})
    else:
        raise KeyError(f"MCP server action `{suffix}` is not supported")


# -- registration ------------------------------------------------------------

register("*", ("api", "v1", "mcp", "servers"), _handle_servers)
register("*", ("api", "v1", "mcp", "servers", "*"), _handle_server)
register("*", ("api", "v1", "mcp", "servers", "*", "*"), _handle_server_action)
