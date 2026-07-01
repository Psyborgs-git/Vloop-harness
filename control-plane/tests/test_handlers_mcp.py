"""Unit tests for cp/handlers/mcp.py routes (Requirement 18.1).

Exercises the MCP server HTTP routes through the real router registration using
a fake HTTP handler (capturing the written JSON response) and a fake runtime
that records the documented accessor calls. The MCP_Client/runtime wiring is
covered elsewhere; here we verify the handler contract:

* GET    /api/v1/mcp/servers                 — list connections (Req 18.1)
* POST   /api/v1/mcp/servers                 — configure a connection (Req 18.1)
* GET    /api/v1/mcp/servers/{id}            — inspect a connection
* PUT    /api/v1/mcp/servers/{id}            — re-configure a connection
* DELETE /api/v1/mcp/servers/{id}            — remove a connection
* POST   /api/v1/mcp/servers/{id}/connect    — connect + register tools (Req 18.1)
* POST   /api/v1/mcp/servers/{id}/disconnect — disconnect (Req 18.3)
"""

from __future__ import annotations

import io
import json
from http import HTTPStatus
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# Importing the module registers its routes on the shared router registry.
import cp.handlers.mcp  # noqa: F401
from cp.handlers.router import route


class FakeHandler:
    """Captures the JSON response written by `write_json`."""

    def __init__(self) -> None:
        self.status: HTTPStatus | int | None = None
        self.headers_sent: dict[str, str] = {}
        self.wfile = io.BytesIO()

    def send_response(self, status: Any) -> None:
        self.status = status

    def send_header(self, key: str, value: str) -> None:
        self.headers_sent[key] = value

    def end_headers(self) -> None:
        pass

    @property
    def body(self) -> Any:
        return json.loads(self.wfile.getvalue().decode("utf-8"))


class FakeRuntime:
    """Records calls to the documented MCP server accessors."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.servers: list[dict[str, Any]] = [
            {"id": "s1", "name": "files", "transport": "stdio", "status": "connected"},
            {"id": "s2", "name": "search", "transport": "http", "status": "disconnected"},
        ]
        self.get_returns_none = False

    def list_mcp_servers(self) -> list[dict[str, Any]]:
        self.calls.append(("list", ()))
        return self.servers

    def configure_mcp_server(self, config: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("configure", (config,)))
        return {
            "id": config.get("id", "new-id"),
            "name": config.get("name", "unnamed"),
            "transport": config.get("transport", "stdio"),
            "status": "disconnected",
        }

    def get_mcp_server(self, server_id: str) -> dict[str, Any] | None:
        self.calls.append(("get", (server_id,)))
        if self.get_returns_none:
            return None
        return {"id": server_id, "name": "files", "transport": "stdio"}

    def remove_mcp_server(self, server_id: str) -> None:
        self.calls.append(("remove", (server_id,)))

    def connect_mcp_server(self, server_id: str) -> dict[str, Any]:
        self.calls.append(("connect", (server_id,)))
        return {"id": server_id, "status": "connected", "tools": ["read", "write"]}

    def disconnect_mcp_server(self, server_id: str) -> dict[str, Any]:
        self.calls.append(("disconnect", (server_id,)))
        return {"id": server_id, "status": "disconnected"}


# ---------------------------------------------------------------------------
# Collection: GET / POST  (Requirement 18.1)
# ---------------------------------------------------------------------------


def test_get_lists_servers():
    handler = FakeHandler()
    runtime = FakeRuntime()
    route(handler, "GET", "/api/v1/mcp/servers", {}, {}, runtime)

    assert handler.status == HTTPStatus.OK
    assert handler.body == {"mcpServers": runtime.servers}
    assert runtime.calls == [("list", ())]


def test_post_configures_server():
    handler = FakeHandler()
    runtime = FakeRuntime()
    body = {"name": "files", "transport": "stdio", "toolFilter": ["read"]}
    route(handler, "POST", "/api/v1/mcp/servers", {}, body, runtime)

    assert handler.status == HTTPStatus.CREATED
    assert handler.body["mcpServer"]["name"] == "files"
    assert runtime.calls == [("configure", (body,))]


def test_collection_rejects_unsupported_method():
    from cp.http_api import MethodNotAllowedError

    handler = FakeHandler()
    runtime = FakeRuntime()
    with pytest.raises(MethodNotAllowedError):
        route(handler, "DELETE", "/api/v1/mcp/servers", {}, {}, runtime)


# ---------------------------------------------------------------------------
# Singleton: GET / PUT / DELETE
# ---------------------------------------------------------------------------


def test_get_single_server():
    handler = FakeHandler()
    runtime = FakeRuntime()
    route(handler, "GET", "/api/v1/mcp/servers/s1", {}, {}, runtime)

    assert handler.status == HTTPStatus.OK
    assert handler.body == {"mcpServer": {"id": "s1", "name": "files", "transport": "stdio"}}
    assert runtime.calls == [("get", ("s1",))]


def test_get_unknown_server_raises_keyerror():
    handler = FakeHandler()
    runtime = FakeRuntime()
    runtime.get_returns_none = True
    with pytest.raises(KeyError):
        route(handler, "GET", "/api/v1/mcp/servers/missing", {}, {}, runtime)


def test_get_single_server_unquotes_id():
    handler = FakeHandler()
    runtime = FakeRuntime()
    route(handler, "GET", "/api/v1/mcp/servers/a%20b", {}, {}, runtime)
    assert runtime.calls == [("get", ("a b",))]


def test_put_reconfigures_and_pins_id():
    handler = FakeHandler()
    runtime = FakeRuntime()
    route(
        handler,
        "PUT",
        "/api/v1/mcp/servers/s1",
        {},
        {"id": "other", "name": "renamed", "transport": "http"},
        runtime,
    )

    assert handler.status == HTTPStatus.OK
    # The path id wins over any id in the body.
    assert runtime.calls == [
        ("configure", ({"id": "s1", "name": "renamed", "transport": "http"},))
    ]
    assert handler.body["mcpServer"]["id"] == "s1"


def test_delete_removes_server():
    handler = FakeHandler()
    runtime = FakeRuntime()
    route(handler, "DELETE", "/api/v1/mcp/servers/s1", {}, {}, runtime)

    assert handler.status == HTTPStatus.OK
    assert handler.body == {"ok": True, "mcpServerId": "s1"}
    assert runtime.calls == [("remove", ("s1",))]


# ---------------------------------------------------------------------------
# Sub-resources: connect / disconnect  (Requirements 18.1, 18.3)
# ---------------------------------------------------------------------------


def test_post_connect_calls_runtime():
    handler = FakeHandler()
    runtime = FakeRuntime()
    route(handler, "POST", "/api/v1/mcp/servers/s1/connect", {}, {}, runtime)

    assert handler.status == HTTPStatus.OK
    assert handler.body == {
        "mcpServer": {"id": "s1", "status": "connected", "tools": ["read", "write"]}
    }
    assert runtime.calls == [("connect", ("s1",))]


def test_post_disconnect_calls_runtime():
    handler = FakeHandler()
    runtime = FakeRuntime()
    route(handler, "POST", "/api/v1/mcp/servers/s1/disconnect", {}, {}, runtime)

    assert handler.status == HTTPStatus.OK
    assert handler.body == {"mcpServer": {"id": "s1", "status": "disconnected"}}
    assert runtime.calls == [("disconnect", ("s1",))]


def test_connect_rejects_get_method():
    from cp.http_api import MethodNotAllowedError

    handler = FakeHandler()
    runtime = FakeRuntime()
    with pytest.raises(MethodNotAllowedError):
        route(handler, "GET", "/api/v1/mcp/servers/s1/connect", {}, {}, runtime)


def test_unknown_action_raises_keyerror():
    handler = FakeHandler()
    runtime = FakeRuntime()
    with pytest.raises(KeyError):
        route(handler, "POST", "/api/v1/mcp/servers/s1/bogus", {}, {}, runtime)


# ---------------------------------------------------------------------------
# Property: listing round-trips the runtime's server list verbatim (Req 18.1)
# ---------------------------------------------------------------------------

_SERVER = st.fixed_dictionaries(
    {
        "id": st.text(min_size=1, max_size=12),
        "name": st.text(max_size=20),
        "transport": st.sampled_from(["stdio", "http", "sse"]),
        "status": st.sampled_from(["connected", "disconnected", "failed"]),
    }
)


@settings(max_examples=200, deadline=None)
@given(servers=st.lists(_SERVER, max_size=8))
def test_list_returns_runtime_servers_verbatim(servers):
    """Feature: orchestration-engine-completion, Property: GET /mcp/servers
    returns exactly the connections the runtime reports (Requirement 18.1)."""
    handler = FakeHandler()
    runtime = FakeRuntime()
    runtime.servers = servers
    route(handler, "GET", "/api/v1/mcp/servers", {}, {}, runtime)

    assert handler.status == HTTPStatus.OK
    assert handler.body == {"mcpServers": servers}
