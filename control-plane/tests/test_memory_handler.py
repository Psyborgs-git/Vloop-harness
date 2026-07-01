"""Unit tests for cp/handlers/memory.py routes.

Exercises the memory HTTP routes through the real router registration using a
fake HTTP handler (capturing the written response) and a fake runtime that
records the accessor calls. Covers:

* GET  /api/v1/memory            — list entries (Requirement 11.4)
* GET  /api/v1/memory?category=  — list filtered by category (Requirement 11.4)
* POST /api/v1/memory            — create entry (Requirement 11.1)
* DELETE /api/v1/memory/{id}     — delete entry (Requirement 11.3)
"""

from __future__ import annotations

import io
import json
from http import HTTPStatus
from typing import Any

# Importing the module registers its routes on the shared router registry.
import cp.handlers.memory  # noqa: F401
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

    def end_headers(self) -> None:  # noqa: D401 - no-op for the fake
        pass

    @property
    def body(self) -> Any:
        return json.loads(self.wfile.getvalue().decode("utf-8"))


class FakeRuntime:
    """Records calls to the documented memory accessors."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.entries: list[dict[str, Any]] = [
            {"id": "m1", "category": "preference", "content": "likes dark mode"},
            {"id": "m2", "category": "project", "content": "uses pytest"},
        ]

    def list_memory_entries(self, *args: Any) -> list[dict[str, Any]]:
        self.calls.append(("list", args))
        category = args[0] if args else None
        if category is None:
            return self.entries
        return [e for e in self.entries if e["category"] == category]

    def record_memory_entry(self, *args: Any) -> dict[str, Any]:
        self.calls.append(("record", args))
        content = args[0]
        category = args[1] if len(args) > 1 else None
        return {
            "id": "new-id",
            "category": category or "preference",
            "content": content,
        }

    def delete_memory_entry(self, *args: Any) -> None:
        self.calls.append(("delete", args))


# ---------------------------------------------------------------------------
# GET /api/v1/memory  (Requirement 11.4)
# ---------------------------------------------------------------------------


def test_list_returns_all_entries():
    handler = FakeHandler()
    runtime = FakeRuntime()
    route(handler, "GET", "/api/v1/memory", {}, {}, runtime)

    assert handler.status == HTTPStatus.OK
    assert handler.body == {"memoryEntries": runtime.entries}
    assert runtime.calls == [("list", (None,))]


def test_list_filters_by_category_query():
    handler = FakeHandler()
    runtime = FakeRuntime()
    route(handler, "GET", "/api/v1/memory", {"category": ["project"]}, {}, runtime)

    assert handler.status == HTTPStatus.OK
    assert handler.body == {
        "memoryEntries": [
            {"id": "m2", "category": "project", "content": "uses pytest"}
        ]
    }
    assert runtime.calls == [("list", ("project",))]


# ---------------------------------------------------------------------------
# POST /api/v1/memory  (Requirement 11.1)
# ---------------------------------------------------------------------------


def test_create_records_entry_with_default_category():
    handler = FakeHandler()
    runtime = FakeRuntime()
    route(handler, "POST", "/api/v1/memory", {}, {"content": "remember this"}, runtime)

    assert handler.status == HTTPStatus.CREATED
    assert handler.body == {
        "memoryEntry": {
            "id": "new-id",
            "category": "preference",
            "content": "remember this",
        }
    }
    assert runtime.calls == [("record", ("remember this",))]


def test_create_records_entry_with_explicit_category():
    handler = FakeHandler()
    runtime = FakeRuntime()
    route(
        handler,
        "POST",
        "/api/v1/memory",
        {},
        {"content": "uses uv", "category": "environment"},
        runtime,
    )

    assert handler.status == HTTPStatus.CREATED
    assert handler.body["memoryEntry"]["category"] == "environment"
    assert runtime.calls == [("record", ("uses uv", "environment"))]


def test_create_requires_content():
    handler = FakeHandler()
    runtime = FakeRuntime()
    try:
        route(handler, "POST", "/api/v1/memory", {}, {}, runtime)
    except ValueError as exc:
        assert "content" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("expected ValueError for missing content")
    assert runtime.calls == []


# ---------------------------------------------------------------------------
# DELETE /api/v1/memory/{id}  (Requirement 11.3)
# ---------------------------------------------------------------------------


def test_delete_removes_entry():
    handler = FakeHandler()
    runtime = FakeRuntime()
    route(handler, "DELETE", "/api/v1/memory/m1", {}, {}, runtime)

    assert handler.status == HTTPStatus.OK
    assert handler.body == {"ok": True, "memoryId": "m1"}
    assert runtime.calls == [("delete", ("m1",))]


def test_delete_unquotes_id():
    handler = FakeHandler()
    runtime = FakeRuntime()
    route(handler, "DELETE", "/api/v1/memory/a%20b", {}, {}, runtime)

    assert handler.body == {"ok": True, "memoryId": "a b"}
    assert runtime.calls == [("delete", ("a b",))]


# ---------------------------------------------------------------------------
# Method gating
# ---------------------------------------------------------------------------


def test_unsupported_collection_method_raises():
    handler = FakeHandler()
    runtime = FakeRuntime()
    try:
        route(handler, "PUT", "/api/v1/memory", {}, {}, runtime)
    except Exception as exc:  # MethodNotAllowedError
        assert "PUT" in str(exc) or "method" in str(exc).lower()
    else:  # pragma: no cover - defensive
        raise AssertionError("expected method-not-allowed error")


def test_unsupported_singleton_method_raises():
    handler = FakeHandler()
    runtime = FakeRuntime()
    try:
        route(handler, "POST", "/api/v1/memory/m1", {}, {}, runtime)
    except Exception as exc:  # MethodNotAllowedError
        assert "POST" in str(exc) or "method" in str(exc).lower()
    else:  # pragma: no cover - defensive
        raise AssertionError("expected method-not-allowed error")
