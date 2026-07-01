"""Unit + property tests for the tool/toolset HTTP routes (cp/handlers/tools.py).

These exercise the route registrations end-to-end through ``cp.handlers.route``
using a fake runtime that records the accessor calls, plus a fake HTTP handler
that captures the status + JSON response. The Tool_Registry/runtime wiring is
covered elsewhere; here we verify the handler contract:

* ``GET  /api/v1/tools``                 lists Tools, optionally per ``?scope=`` (Req 9.1)
* ``GET  /api/v1/toolsets``              lists Toolsets, optionally per ``?scope=`` (Req 9.1)
* ``POST /api/v1/tools/{name}/enable``   enables a Tool's toolset in a scope (Req 9.2)
* ``POST /api/v1/tools/{name}/disable``  disables a Tool's toolset in a scope (Req 9.2)
* ``POST /api/v1/toolsets/{id}/enable``  enables a Toolset in a scope (Req 9.2)
* ``POST /api/v1/toolsets/{id}/disable`` disables a Toolset in a scope (Req 9.2)
* missing scope → ValueError (→ 400); unknown action → KeyError (→ 404);
  wrong method → MethodNotAllowedError
"""

from __future__ import annotations

import json
from http import HTTPStatus
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import cp.handlers  # noqa: F401 — triggers route registration side effects
from cp.handlers import route
from cp.http_api import MethodNotAllowedError


class FakeRuntime:
    """Records tool/toolset accessor calls and returns canned values."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.unknown_tool: bool = False
        self.unknown_toolset: bool = False

    def list_tools(self, *, scope: str | None = None):
        self.calls.append(("list_tools", (), {"scope": scope}))
        return [{"name": "web_search", "toolset": "research", "enabled": True}]

    def list_toolsets(self, *, scope: str | None = None):
        self.calls.append(("list_toolsets", (), {"scope": scope}))
        return [{"id": "research", "name": "Research", "enabled": True}]

    def set_tool_enabled(self, tool_name: str, scope: str, enabled: bool):
        self.calls.append(
            ("set_tool_enabled", (tool_name, scope, enabled), {})
        )
        if self.unknown_tool:
            raise KeyError(f"tool `{tool_name}` was not found")
        return {"name": tool_name, "scope": scope, "enabled": enabled}

    def set_toolset_enabled(self, toolset_id: str, scope: str, enabled: bool):
        self.calls.append(
            ("set_toolset_enabled", (toolset_id, scope, enabled), {})
        )
        if self.unknown_toolset:
            raise KeyError(f"toolset `{toolset_id}` was not found")
        return {"id": toolset_id, "scope": scope, "enabled": enabled}


class _FakeWFile:
    def __init__(self) -> None:
        self.chunks: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.chunks.append(data)


class FakeHandler:
    """Minimal stand-in for BaseHTTPRequestHandler used by write_json."""

    def __init__(self) -> None:
        self.status: HTTPStatus | None = None
        self.headers_sent: dict[str, str] = {}
        self.wfile = _FakeWFile()

    def send_response(self, status: HTTPStatus) -> None:
        self.status = status

    def send_header(self, key: str, value: str) -> None:
        self.headers_sent[key] = value

    def end_headers(self) -> None:
        pass

    @property
    def body(self) -> Any:
        return json.loads(b"".join(self.wfile.chunks).decode("utf-8"))


def _dispatch(method, path, *, query=None, body=None, runtime=None):
    """Route a request and return (handler, runtime)."""
    runtime = runtime if runtime is not None else FakeRuntime()
    handler = FakeHandler()
    route(handler, method, path, query or {}, body or {}, runtime)
    return handler, runtime


# ---------------------------------------------------------------------------
# Listing (Requirement 9.1)
# ---------------------------------------------------------------------------


def test_get_lists_tools_without_scope():
    handler, runtime = _dispatch("GET", "/api/v1/tools")
    assert handler.status == HTTPStatus.OK
    assert handler.body == {
        "tools": [{"name": "web_search", "toolset": "research", "enabled": True}]
    }
    assert runtime.calls == [("list_tools", (), {"scope": None})]


def test_get_lists_tools_passes_scope_query():
    _, runtime = _dispatch("GET", "/api/v1/tools", query={"scope": ["agent-7"]})
    assert runtime.calls == [("list_tools", (), {"scope": "agent-7"})]


def test_get_lists_toolsets_without_scope():
    handler, runtime = _dispatch("GET", "/api/v1/toolsets")
    assert handler.status == HTTPStatus.OK
    assert handler.body == {
        "toolsets": [{"id": "research", "name": "Research", "enabled": True}]
    }
    assert runtime.calls == [("list_toolsets", (), {"scope": None})]


def test_get_lists_toolsets_passes_scope_query():
    _, runtime = _dispatch(
        "GET", "/api/v1/toolsets", query={"scope": ["run-3"]}
    )
    assert runtime.calls == [("list_toolsets", (), {"scope": "run-3"})]


# ---------------------------------------------------------------------------
# Enable / disable Tools (Requirement 9.2)
# ---------------------------------------------------------------------------


def test_post_enable_tool_calls_runtime():
    handler, runtime = _dispatch(
        "POST", "/api/v1/tools/web_search/enable", body={"scope": "agent-1"}
    )
    assert handler.status == HTTPStatus.OK
    assert handler.body == {
        "tool": {"name": "web_search", "scope": "agent-1", "enabled": True}
    }
    assert runtime.calls == [
        ("set_tool_enabled", ("web_search", "agent-1", True), {})
    ]


def test_post_disable_tool_calls_runtime():
    handler, runtime = _dispatch(
        "POST", "/api/v1/tools/web_search/disable", body={"scope": "agent-1"}
    )
    assert handler.status == HTTPStatus.OK
    assert runtime.calls == [
        ("set_tool_enabled", ("web_search", "agent-1", False), {})
    ]


def test_post_enable_tool_decodes_name():
    _, runtime = _dispatch(
        "POST", "/api/v1/tools/web%2Fsearch/enable", body={"scope": "s"}
    )
    assert runtime.calls == [
        ("set_tool_enabled", ("web/search", "s", True), {})
    ]


def test_post_enable_tool_requires_scope():
    with pytest.raises(ValueError):
        _dispatch("POST", "/api/v1/tools/web_search/enable", body={})


def test_post_tool_unknown_action_raises_keyerror():
    with pytest.raises(KeyError):
        _dispatch(
            "POST", "/api/v1/tools/web_search/bogus", body={"scope": "s"}
        )


def test_post_tool_unknown_tool_raises_keyerror():
    runtime = FakeRuntime()
    runtime.unknown_tool = True
    with pytest.raises(KeyError):
        _dispatch(
            "POST",
            "/api/v1/tools/missing/enable",
            body={"scope": "s"},
            runtime=runtime,
        )


def test_enable_tool_rejects_get_method():
    with pytest.raises(MethodNotAllowedError):
        _dispatch("GET", "/api/v1/tools/web_search/enable", body={"scope": "s"})


def test_list_tools_rejects_post_method():
    with pytest.raises(MethodNotAllowedError):
        _dispatch("POST", "/api/v1/tools")


# ---------------------------------------------------------------------------
# Enable / disable Toolsets (Requirement 9.2)
# ---------------------------------------------------------------------------


def test_post_enable_toolset_calls_runtime():
    handler, runtime = _dispatch(
        "POST", "/api/v1/toolsets/research/enable", body={"scope": "run-1"}
    )
    assert handler.status == HTTPStatus.OK
    assert handler.body == {
        "toolset": {"id": "research", "scope": "run-1", "enabled": True}
    }
    assert runtime.calls == [
        ("set_toolset_enabled", ("research", "run-1", True), {})
    ]


def test_post_disable_toolset_calls_runtime():
    _, runtime = _dispatch(
        "POST", "/api/v1/toolsets/research/disable", body={"scope": "run-1"}
    )
    assert runtime.calls == [
        ("set_toolset_enabled", ("research", "run-1", False), {})
    ]


def test_post_enable_toolset_requires_scope():
    with pytest.raises(ValueError):
        _dispatch("POST", "/api/v1/toolsets/research/enable", body={})


def test_post_toolset_unknown_action_raises_keyerror():
    with pytest.raises(KeyError):
        _dispatch(
            "POST", "/api/v1/toolsets/research/bogus", body={"scope": "s"}
        )


def test_post_toolset_unknown_toolset_raises_keyerror():
    runtime = FakeRuntime()
    runtime.unknown_toolset = True
    with pytest.raises(KeyError):
        _dispatch(
            "POST",
            "/api/v1/toolsets/missing/enable",
            body={"scope": "s"},
            runtime=runtime,
        )


def test_enable_toolset_rejects_get_method():
    with pytest.raises(MethodNotAllowedError):
        _dispatch("GET", "/api/v1/toolsets/research/enable", body={"scope": "s"})


# ---------------------------------------------------------------------------
# Property: enable/disable action maps to the correct enabled boolean per scope
# ---------------------------------------------------------------------------

# Feature: orchestration-engine-completion, Property: the enable/disable action
# segment deterministically forwards the matching enabled boolean, the decoded
# resource name, and the body scope to the Tool_Registry accessor (Req 9.2).
_NAME = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="/"),
    min_size=1,
    max_size=24,
).filter(lambda s: s.strip() and "%" not in s)
# scope is forwarded through required_string(), which strips surrounding
# whitespace; generate already-stripped values so the strategy matches what the
# accessor receives.
_SCOPE = st.text(min_size=1, max_size=24).map(str.strip).filter(lambda s: s)


@settings(max_examples=200)
@given(name=_NAME, scope=_SCOPE, action=st.sampled_from(["enable", "disable"]))
def test_tool_action_forwards_scope_and_enabled(name, scope, action):
    runtime = FakeRuntime()
    handler = FakeHandler()
    route(
        handler,
        "POST",
        f"/api/v1/tools/{name}/{action}",
        {},
        {"scope": scope},
        runtime,
    )
    assert handler.status == HTTPStatus.OK
    assert runtime.calls == [
        ("set_tool_enabled", (name, scope, action == "enable"), {})
    ]
    assert handler.body == {
        "tool": {"name": name, "scope": scope, "enabled": action == "enable"}
    }


@settings(max_examples=200)
@given(tid=_NAME, scope=_SCOPE, action=st.sampled_from(["enable", "disable"]))
def test_toolset_action_forwards_scope_and_enabled(tid, scope, action):
    runtime = FakeRuntime()
    handler = FakeHandler()
    route(
        handler,
        "POST",
        f"/api/v1/toolsets/{tid}/{action}",
        {},
        {"scope": scope},
        runtime,
    )
    assert handler.status == HTTPStatus.OK
    assert runtime.calls == [
        ("set_toolset_enabled", (tid, scope, action == "enable"), {})
    ]
