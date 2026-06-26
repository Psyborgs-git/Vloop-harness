"""System routes: health, session, events, window, dependencies, bootstrap, usage, shutdown."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

from cp.handlers.router import register

from cp.http_responders import write_error_json, write_json
from cp.http_utils import require_method, split_segments

# These handlers assume they are called from within a
# `BaseHTTPRequestHandler` instance — i.e. the first positional arg
# (`handler`) is the handler *self* (like `cp.http_handler` used to pass).


# ---------------------------------------------------------------------------
# Top-level short routes (non-/api/ prefixed)
# ---------------------------------------------------------------------------


def _handle_system_health(
    handler: Any, _method: str, _path: str, _query: Any, _body: Any, runtime: Any
) -> None:
    write_json(handler, runtime.health_snapshot())


def _handle_system_session(
    handler: Any, _method: str, _path: str, _query: Any, _body: Any, runtime: Any
) -> None:
    write_json(handler, runtime.session_snapshot())


def _handle_system_events(
    handler: Any, _method: str, _path: str, _query: Any, _body: Any, runtime: Any
) -> None:
    write_json(handler, runtime.event_snapshot())


def _handle_system_window(
    handler: Any, _method: str, _path: str, _query: Any, _body: Any, runtime: Any
) -> None:
    write_json(handler, runtime.window_snapshot())


def _handle_system_deps(
    handler: Any, _method: str, _path: str, _query: Any, _body: Any, runtime: Any
) -> None:
    write_json(handler, runtime.dependency_snapshot())


def _handle_shutdown(
    handler: Any, _method: str, _path: str, _query: Any, _body: Any, runtime: Any
) -> None:
    runtime.request_shutdown()
    runtime.window_manager.shutdown("user requested quit from UI")
    write_json(handler, {"ok": True})


# ---------------------------------------------------------------------------
# API-prefixed system routes
# ---------------------------------------------------------------------------


def _handle_bootstrap(
    handler: Any, method: str, _path: str, _query: Any, _body: Any, runtime: Any
) -> None:
    """GET /api/v1, /api/v1/bootstrap, /api/v1/state"""
    require_method(method, {"GET"})
    write_json(handler, runtime.bootstrap_payload())


def _handle_system_snapshot(
    handler: Any, method: str, _path: str, _query: Any, _body: Any, runtime: Any
) -> None:
    """GET /api/v1/system"""
    require_method(method, {"GET"})
    write_json(handler, runtime.system_snapshot())


def _handle_usage(
    handler: Any, method: str, _path: str, _query: Any, _body: Any, runtime: Any
) -> None:
    """GET /api/v1/usage"""
    require_method(method, {"GET"})
    write_json(handler, runtime.get_usage_stats())


# -- registration ------------------------------------------------------------

_TOP_LEVEL = [
    ("GET", ("health",), _handle_system_health),
    ("GET", ("session",), _handle_system_session),
    ("GET", ("events", "recent"), _handle_system_events),
    ("GET", ("window",), _handle_system_window),
    ("GET", ("dependencies",), _handle_system_deps),
    ("POST", ("shutdown",), _handle_shutdown),
]

_API = [
    ("*", ("api", "v1"), _handle_bootstrap),
    ("*", ("api", "v1", "bootstrap"), _handle_bootstrap),
    ("*", ("api", "v1", "state"), _handle_bootstrap),
    ("*", ("api", "v1", "system"), _handle_system_snapshot),
    ("*", ("api", "v1", "usage"), _handle_usage),
]

for meth, pattern, func in _TOP_LEVEL + _API:
    register(meth, pattern, func)
