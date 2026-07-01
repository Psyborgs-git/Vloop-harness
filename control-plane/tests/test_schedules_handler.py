"""Unit tests for the scheduled-task HTTP routes (cp/handlers/schedules.py).

These exercise the route registrations end-to-end through ``cp.handlers.route``
using a fake runtime that records the accessor calls, plus a fake HTTP handler
that captures the JSON response. The Scheduler/runtime wiring itself is covered
elsewhere; here we verify the handler contract:

* ``GET /api/v1/schedules`` lists tasks (Requirement 14.1)
* ``POST /api/v1/schedules`` creates a task in active or paused state (Req 14.1)
* ``POST /api/v1/schedules/{id}/pause`` pauses a task (Requirement 14.3)
* ``POST /api/v1/schedules/{id}/resume`` resumes a task (Requirement 14.3)
* invalid creation state and invalid cron expressions become 400 responses
  (Requirement 14.5)
"""

from __future__ import annotations

import json
from http import HTTPStatus
from typing import Any

import pytest

import cp.handlers  # noqa: F401 — triggers route registration side effects
from cp.handlers import route
from cp.http_handler import handler_factory


class FakeRuntime:
    """Records scheduled-task accessor calls and returns canned values."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.create_error: Exception | None = None

    def list_scheduled_tasks(self, *, definition_id: str | None = None):
        self.calls.append(("list", (), {"definition_id": definition_id}))
        return [{"id": "t1", "definition_id": "def-1", "state": "active"}]

    def create_scheduled_task(self, definition_id, cron_expression, *, state="active"):
        self.calls.append(
            ("create", (definition_id, cron_expression), {"state": state})
        )
        if self.create_error is not None:
            raise self.create_error
        return {
            "id": "new-task",
            "definition_id": definition_id,
            "cron_expression": cron_expression,
            "state": state,
        }

    def pause_scheduled_task(self, task_id):
        self.calls.append(("pause", (task_id,), {}))
        return {"id": task_id, "state": "paused"}

    def resume_scheduled_task(self, task_id):
        self.calls.append(("resume", (task_id,), {}))
        return {"id": task_id, "state": "active"}


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


def _dispatch(method, path, *, query=None, body=None):
    """Route a request and return (handler, runtime). Mirrors http_handler."""
    runtime = FakeRuntime()
    handler = FakeHandler()
    route(handler, method, path, query or {}, body or {}, runtime)
    return handler, runtime


def _dispatch_with_runtime(method, path, runtime, *, query=None, body=None):
    handler = FakeHandler()
    route(handler, method, path, query or {}, body or {}, runtime)
    return handler


# ---------------------------------------------------------------------------
# Listing (Requirement 14.1)
# ---------------------------------------------------------------------------


def test_get_lists_scheduled_tasks():
    handler, runtime = _dispatch("GET", "/api/v1/schedules")
    assert handler.status == HTTPStatus.OK
    assert handler.body == {
        "scheduledTasks": [
            {"id": "t1", "definition_id": "def-1", "state": "active"}
        ]
    }
    assert runtime.calls == [("list", (), {"definition_id": None})]


def test_get_passes_definition_filter_from_query():
    _, runtime = _dispatch(
        "GET", "/api/v1/schedules", query={"definitionId": ["def-9"]}
    )
    assert runtime.calls == [("list", (), {"definition_id": "def-9"})]


# ---------------------------------------------------------------------------
# Creation (Requirement 14.1)
# ---------------------------------------------------------------------------


def test_post_creates_active_task_by_default():
    handler, runtime = _dispatch(
        "POST",
        "/api/v1/schedules",
        body={"definitionId": "def-1", "cronExpression": "*/5 * * * *"},
    )
    assert handler.status == HTTPStatus.CREATED
    assert handler.body["scheduledTask"]["state"] == "active"
    assert runtime.calls == [
        ("create", ("def-1", "*/5 * * * *"), {"state": "active"})
    ]


def test_post_creates_paused_task_when_requested():
    handler, runtime = _dispatch(
        "POST",
        "/api/v1/schedules",
        body={
            "definitionId": "def-1",
            "cronExpression": "0 9 * * *",
            "state": "paused",
        },
    )
    assert handler.status == HTTPStatus.CREATED
    assert runtime.calls == [
        ("create", ("def-1", "0 9 * * *"), {"state": "paused"})
    ]


def test_post_rejects_unknown_state():
    with pytest.raises(ValueError):
        _dispatch(
            "POST",
            "/api/v1/schedules",
            body={
                "definitionId": "def-1",
                "cronExpression": "0 9 * * *",
                "state": "bogus",
            },
        )


def test_post_requires_definition_and_cron():
    with pytest.raises(ValueError):
        _dispatch("POST", "/api/v1/schedules", body={"definitionId": "def-1"})


def test_post_invalid_cron_maps_to_bad_request():
    """A CronParseError (ValueError) is surfaced as HTTP 400 by the shell."""
    runtime = FakeRuntime()
    from core.cron_parser import CronParseError

    runtime.create_error = CronParseError("bad cron")

    factory = handler_factory(runtime)
    # Build a real ControlPlaneHandler without running __init__/socket setup.
    real_handler = factory.__new__(factory)
    wfile = _FakeWFile()
    captured: dict[str, Any] = {}

    def send_response(status):
        captured["status"] = status

    real_handler.send_response = send_response  # type: ignore[method-assign]
    real_handler.send_header = lambda *a, **k: None  # type: ignore[method-assign]
    real_handler.end_headers = lambda: None  # type: ignore[method-assign]
    real_handler.wfile = wfile  # type: ignore[assignment]

    err = CronParseError("bad cron")
    real_handler._handle_exception(err)  # type: ignore[attr-defined]
    assert captured["status"] == HTTPStatus.BAD_REQUEST


# ---------------------------------------------------------------------------
# Pause / resume (Requirement 14.3)
# ---------------------------------------------------------------------------


def test_post_pause_calls_runtime():
    handler, runtime = _dispatch("POST", "/api/v1/schedules/task-7/pause")
    assert handler.status == HTTPStatus.OK
    assert handler.body == {"scheduledTask": {"id": "task-7", "state": "paused"}}
    assert runtime.calls == [("pause", ("task-7",), {})]


def test_post_resume_calls_runtime():
    handler, runtime = _dispatch("POST", "/api/v1/schedules/task-7/resume")
    assert handler.status == HTTPStatus.OK
    assert handler.body == {"scheduledTask": {"id": "task-7", "state": "active"}}
    assert runtime.calls == [("resume", ("task-7",), {})]


def test_unknown_action_raises_keyerror():
    runtime = FakeRuntime()
    with pytest.raises(KeyError):
        _dispatch_with_runtime("POST", "/api/v1/schedules/task-7/bogus", runtime)


def test_pause_rejects_get_method():
    from cp.http_api import MethodNotAllowedError

    runtime = FakeRuntime()
    with pytest.raises(MethodNotAllowedError):
        _dispatch_with_runtime("GET", "/api/v1/schedules/task-7/pause", runtime)
