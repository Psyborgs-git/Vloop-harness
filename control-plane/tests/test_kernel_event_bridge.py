"""Tests for the KernelEventRouter bridge to the orchestration Event_Router.

Verifies that the existing kernel event router keeps working without an
Event_Router (backward compatibility) and, when wired to one, bridges
run-attributable kernel events and internal orchestration events into the
``workflow_events`` stream (task 8.1, Requirements 4.1, 21.4, 21.5).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.database import SQLiteBackend
from core.event_router import EventRouter, WorkflowEventType
from cp.events import KernelEventRouter, start_event_router


class _FakeWindowManager:
    def __init__(self) -> None:
        self.opened: list[str] = []

    def open_main_window(self, reason: str) -> None:
        self.opened.append(reason)


class _FakeKernelEvent:
    def __init__(self, **kwargs):
        self.event_id = kwargs.get("event_id", "evt-1")
        self.event_type = kwargs.get("event_type", "")
        self.resource_type = kwargs.get("resource_type", "")
        self.resource_id = kwargs.get("resource_id", "")
        self.status = kwargs.get("status", "")
        self.message = kwargs.get("message", "")
        self.timestamp_unix_ms = kwargs.get("timestamp_unix_ms", 0)
        self.attributes = kwargs.get("attributes", {})


@pytest.fixture()
def backend(tmp_path: Path) -> SQLiteBackend:
    return SQLiteBackend(tmp_path / "bridge-test.db")


# ---------------------------------------------------------------------------
# Backward compatibility (no Event_Router)
# ---------------------------------------------------------------------------


def test_router_without_event_router_still_records_and_opens_ui():
    window = _FakeWindowManager()
    router = start_event_router(window, max_events=10)

    record = router.handle_proto_event(
        _FakeKernelEvent(
            event_type="control_plane.open_ui_requested",
            message="please open",
        )
    )
    assert record.event_type == "control_plane.open_ui_requested"
    assert window.opened == ["please open"]
    assert router.snapshot()["event_count"] == 1


def test_handle_orchestration_event_no_op_without_event_router():
    router = start_event_router(_FakeWindowManager())
    assert router.handle_orchestration_event("run-1", "x", "msg") is None


# ---------------------------------------------------------------------------
# Bridged behavior (with Event_Router)
# ---------------------------------------------------------------------------


def test_kernel_event_with_run_id_is_bridged(backend: SQLiteBackend):
    event_router = EventRouter(backend)
    router = KernelEventRouter(_FakeWindowManager(), event_router=event_router)

    router.handle_proto_event(
        _FakeKernelEvent(
            event_type="workload.started",
            resource_id="wl-1",
            message="sandbox up",
            attributes={"run_id": "run-1", "step_id": "s1"},
        )
    )
    history = event_router.history("run-1")
    assert len(history) == 1
    assert history[0].step_id == "s1"
    assert history[0].type == WorkflowEventType.KERNEL_EVENT


def test_kernel_event_without_run_id_is_not_bridged(backend: SQLiteBackend):
    event_router = EventRouter(backend)
    router = KernelEventRouter(_FakeWindowManager(), event_router=event_router)

    router.handle_proto_event(
        _FakeKernelEvent(event_type="workload.started", attributes={})
    )
    # No run association -> no workflow event persisted, but kernel record kept.
    assert router.snapshot()["event_count"] == 1
    assert backend.fetch_all("SELECT * FROM workflow_events") == []


def test_handle_orchestration_event_emits_and_redacts(backend: SQLiteBackend):
    event_router = EventRouter(backend)
    router = KernelEventRouter(_FakeWindowManager(), event_router=event_router)

    event = router.handle_orchestration_event(
        "run-1",
        WorkflowEventType.STEP_STATE_CHANGED,
        "step ran",
        step_id="s1",
        payload={"api_key": "secret", "ok": "v"},
    )
    assert event is not None
    assert event.payload["api_key"] == "[REDACTED]"
    assert event.payload["ok"] == "v"
    assert len(event_router.history("run-1")) == 1
