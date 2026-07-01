"""Unit tests for cp.handlers.checkpoints route handlers.

Covers:
* GET  /api/v1/runs/{run_id}/checkpoints       -> runtime.list_checkpoints (Req 13.3)
* POST /api/v1/checkpoints/{checkpoint_id}/rollback -> runtime.restore_checkpoint (Req 13.2)

The handlers are exercised both directly and through the shared router to
confirm the route registrations resolve to the correct handler. A fake HTTP
handler records the JSON response and a fake runtime records the accessor calls.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

import cp.handlers  # noqa: F401 - ensures route registrations run
from cp.handlers import route
from cp.handlers.checkpoints import (
    _handle_checkpoint_rollback,
    _handle_run_checkpoints,
)


class FakeHandler:
    """Minimal stand-in for the HTTP handler that captures the response."""

    def __init__(self) -> None:
        self.status: Any = None
        self.headers: dict[str, str] = {}
        self._chunks: list[bytes] = []
        self.wfile = self

    # write_json calls these in order:
    def send_response(self, status: Any) -> None:
        self.status = status

    def send_header(self, key: str, value: str) -> None:
        self.headers[key] = value

    def end_headers(self) -> None:  # pragma: no cover - trivial
        pass

    def write(self, data: bytes) -> None:
        self._chunks.append(data)

    @property
    def json(self) -> Any:
        return json.loads(b"".join(self._chunks).decode("utf-8"))


class FakeRuntime:
    """Records calls to the checkpoint accessor methods."""

    def __init__(
        self,
        checkpoints: list[dict[str, Any]] | None = None,
        restored: dict[str, Any] | None = None,
    ) -> None:
        self._checkpoints = checkpoints if checkpoints is not None else []
        self._restored = restored or {}
        self.list_calls: list[str] = []
        self.restore_calls: list[str] = []

    def list_checkpoints(self, run_id: str) -> list[dict[str, Any]]:
        self.list_calls.append(run_id)
        return self._checkpoints

    def restore_checkpoint(self, checkpoint_id: str) -> dict[str, Any]:
        self.restore_calls.append(checkpoint_id)
        return self._restored


def test_list_checkpoints_returns_run_checkpoints():
    """GET run checkpoints forwards run_id and returns the recorded list (Req 13.3)."""
    rows = [
        {"id": "c1", "run_id": "run-1", "workspace_id": "ws-1"},
        {"id": "c2", "run_id": "run-1", "workspace_id": "ws-1"},
    ]
    runtime = FakeRuntime(checkpoints=rows)
    handler = FakeHandler()

    _handle_run_checkpoints(
        handler, "GET", "/api/v1/runs/run-1/checkpoints", {}, {}, runtime
    )

    assert runtime.list_calls == ["run-1"]
    assert handler.json == {"checkpoints": rows, "runId": "run-1"}


def test_list_checkpoints_empty_is_valid():
    """A run with zero checkpoints lists an empty list (Req 13.3 / 13.4)."""
    runtime = FakeRuntime(checkpoints=[])
    handler = FakeHandler()

    _handle_run_checkpoints(
        handler, "GET", "/api/v1/runs/run-9/checkpoints", {}, {}, runtime
    )

    assert runtime.list_calls == ["run-9"]
    assert handler.json == {"checkpoints": [], "runId": "run-9"}


def test_list_checkpoints_decodes_run_id():
    """Percent-encoded run ids are decoded before being forwarded."""
    runtime = FakeRuntime(checkpoints=[])
    handler = FakeHandler()

    _handle_run_checkpoints(
        handler, "GET", "/api/v1/runs/run%2F1/checkpoints", {}, {}, runtime
    )

    assert runtime.list_calls == ["run/1"]


def test_list_checkpoints_rejects_non_get():
    """Only GET is allowed for listing checkpoints."""
    from cp.http_api import MethodNotAllowedError

    runtime = FakeRuntime()
    handler = FakeHandler()

    with pytest.raises(MethodNotAllowedError):
        _handle_run_checkpoints(
            handler, "POST", "/api/v1/runs/run-1/checkpoints", {}, {}, runtime
        )
    assert runtime.list_calls == []


def test_rollback_requests_restore():
    """POST rollback forwards checkpoint_id to restore_checkpoint (Req 13.2)."""
    restored = {"id": "c1", "run_id": "run-1", "workspace_id": "ws-1"}
    runtime = FakeRuntime(restored=restored)
    handler = FakeHandler()

    _handle_checkpoint_rollback(
        handler, "POST", "/api/v1/checkpoints/c1/rollback", {}, {}, runtime
    )

    assert runtime.restore_calls == ["c1"]
    assert handler.json == {"checkpoint": restored}


def test_rollback_rejects_non_post():
    """Only POST is allowed for rollback."""
    from cp.http_api import MethodNotAllowedError

    runtime = FakeRuntime()
    handler = FakeHandler()

    with pytest.raises(MethodNotAllowedError):
        _handle_checkpoint_rollback(
            handler, "GET", "/api/v1/checkpoints/c1/rollback", {}, {}, runtime
        )
    assert runtime.restore_calls == []


def test_router_dispatches_list_checkpoints():
    """The registered route resolves to the listing handler."""
    runtime = FakeRuntime(checkpoints=[{"id": "c1"}])
    handler = FakeHandler()

    route(handler, "GET", "/api/v1/runs/run-1/checkpoints", {}, {}, runtime)

    assert runtime.list_calls == ["run-1"]
    assert handler.json["checkpoints"] == [{"id": "c1"}]


def test_router_dispatches_rollback():
    """The registered route resolves to the rollback handler."""
    runtime = FakeRuntime(restored={"id": "c1"})
    handler = FakeHandler()

    route(handler, "POST", "/api/v1/checkpoints/c1/rollback", {}, {}, runtime)

    assert runtime.restore_calls == ["c1"]
    assert handler.json["checkpoint"] == {"id": "c1"}
