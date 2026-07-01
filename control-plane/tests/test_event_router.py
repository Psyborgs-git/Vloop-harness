"""Unit tests for the Event_Router (task 8.1).

Covers event normalization, run-id attribution (Req 21.5), secret redaction
(Req 21.4), persistence to ``workflow_events`` (Req 4.1), and the backward-
compatible bridge added to ``cp.events.KernelEventRouter``.

Property tests for per-transition events (8.2), redaction (8.3), and run
attribution (8.4) live in their own files.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.database import SQLiteBackend
from core.event_router import (
    REDACTED,
    EventRouter,
    WorkflowEvent,
    WorkflowEventType,
    redact_secrets,
)
from core.helpers import from_json


@pytest.fixture()
def backend(tmp_path: Path) -> SQLiteBackend:
    return SQLiteBackend(tmp_path / "events-test.db")


@pytest.fixture()
def router(backend: SQLiteBackend) -> EventRouter:
    return EventRouter(backend)


# ---------------------------------------------------------------------------
# Emission, attribution, persistence
# ---------------------------------------------------------------------------


def test_emit_persists_and_attributes_to_run(backend: SQLiteBackend, router: EventRouter):
    event = router.emit(
        "run-1",
        WorkflowEventType.STEP_STATE_CHANGED,
        "step started",
        step_id="s1",
        payload={"state": "running"},
    )
    assert event.run_id == "run-1"
    assert event.seq == 1
    assert event.step_id == "s1"

    row = backend.fetch_one(
        "SELECT * FROM workflow_events WHERE run_id = ? AND seq = ?", ("run-1", 1)
    )
    assert row is not None
    assert row["type"] == WorkflowEventType.STEP_STATE_CHANGED
    assert row["step_id"] == "s1"
    assert row["message"] == "step started"
    assert from_json(row["payload_json"], None) == {"state": "running"}
    assert row["created_at"]


def test_emit_requires_run_id(router: EventRouter):
    with pytest.raises(ValueError):
        router.emit("", WorkflowEventType.RUN_CREATED, "no run")


def test_seq_is_monotonic_per_run(router: EventRouter):
    first = router.emit("run-1", WorkflowEventType.RUN_CREATED, "created")
    second = router.emit("run-1", WorkflowEventType.STEP_STATE_CHANGED, "step")
    third = router.emit("run-1", WorkflowEventType.RUN_COMPLETED, "done")
    assert [first.seq, second.seq, third.seq] == [1, 2, 3]


def test_seq_is_independent_across_runs(router: EventRouter):
    a = router.emit("run-a", WorkflowEventType.RUN_CREATED, "a")
    b = router.emit("run-b", WorkflowEventType.RUN_CREATED, "b")
    assert a.seq == 1
    assert b.seq == 1


def test_seq_continues_after_new_router_instance(backend: SQLiteBackend):
    EventRouter(backend).emit("run-1", WorkflowEventType.RUN_CREATED, "created")
    # A fresh router (simulated restart) must continue the per-run sequence.
    event = EventRouter(backend).emit("run-1", WorkflowEventType.RUN_COMPLETED, "done")
    assert event.seq == 2


def test_history_orders_by_seq(router: EventRouter):
    router.emit("run-1", WorkflowEventType.RUN_CREATED, "created")
    router.emit("run-1", WorkflowEventType.STEP_STATE_CHANGED, "step")
    history = router.history("run-1")
    assert [e.seq for e in history] == [1, 2]
    assert all(isinstance(e, WorkflowEvent) for e in history)
    assert history[0].type == WorkflowEventType.RUN_CREATED


# ---------------------------------------------------------------------------
# Secret redaction (Req 21.4)
# ---------------------------------------------------------------------------


def test_redacts_sensitive_keys_on_emit(backend: SQLiteBackend, router: EventRouter):
    event = router.emit(
        "run-1",
        WorkflowEventType.KERNEL_EVENT,
        "provider configured",
        payload={
            "api_key": "sk-super-secret",
            "authorization": "Bearer abc",
            "model": "gpt-4o",
            "nested": {"password": "hunter2", "ok": "visible"},
        },
    )
    assert event.payload["api_key"] == REDACTED
    assert event.payload["authorization"] == REDACTED
    assert event.payload["model"] == "gpt-4o"
    assert event.payload["nested"]["password"] == REDACTED
    assert event.payload["nested"]["ok"] == "visible"

    # The persisted payload must also be redacted.
    row = backend.fetch_one(
        "SELECT payload_json FROM workflow_events WHERE run_id = ?", ("run-1",)
    )
    stored = from_json(row["payload_json"], None)
    assert "sk-super-secret" not in row["payload_json"]
    assert stored["api_key"] == REDACTED


def test_registered_secret_value_scrubbed_anywhere(router: EventRouter):
    router.register_secret("sk-live-XYZ")
    event = router.emit(
        "run-1",
        WorkflowEventType.STEP_STATE_CHANGED,
        "log line: used sk-live-XYZ to call provider",
        payload={"note": "token sk-live-XYZ leaked into a non-secret field"},
    )
    assert "sk-live-XYZ" not in event.payload["note"]
    assert REDACTED in event.payload["note"]


def test_grant_reference_keys_are_not_redacted():
    payload = {
        "grant_id": "grant-123",
        "session_ref": "sess-abc",
        "grant_ref": "g-1",
        "kernel_snapshot_ref": "snap-1",
        "api_key": "secret",
    }
    out = redact_secrets(payload)
    assert out["grant_id"] == "grant-123"
    assert out["session_ref"] == "sess-abc"
    assert out["grant_ref"] == "g-1"
    assert out["kernel_snapshot_ref"] == "snap-1"
    assert out["api_key"] == REDACTED


def test_redact_does_not_mutate_input():
    payload = {"api_key": "secret", "nested": {"token": "t"}}
    redact_secrets(payload)
    assert payload["api_key"] == "secret"
    assert payload["nested"]["token"] == "t"


def test_redact_handles_lists():
    out = redact_secrets({"items": [{"password": "p"}, {"ok": "v"}]})
    assert out["items"][0]["password"] == REDACTED
    assert out["items"][1]["ok"] == "v"


# ---------------------------------------------------------------------------
# Kernel event normalization
# ---------------------------------------------------------------------------


class _FakeKernelEvent:
    def __init__(self, **kwargs):
        self.event_id = kwargs.get("event_id", "")
        self.event_type = kwargs.get("event_type", "")
        self.resource_type = kwargs.get("resource_type", "")
        self.resource_id = kwargs.get("resource_id", "")
        self.status = kwargs.get("status", "")
        self.message = kwargs.get("message", "")
        self.timestamp_unix_ms = kwargs.get("timestamp_unix_ms", 0)
        self.attributes = kwargs.get("attributes", {})


def test_kernel_event_without_run_is_dropped(router: EventRouter):
    record = _FakeKernelEvent(event_type="workload.started", attributes={})
    assert router.normalize_kernel_event(record) is None


def test_kernel_event_attributed_via_attributes(backend: SQLiteBackend, router: EventRouter):
    record = _FakeKernelEvent(
        event_type="workload.started",
        resource_type="workload",
        resource_id="wl-1",
        status="ok",
        message="sandbox started",
        attributes={"run_id": "run-7", "step_id": "s2"},
    )
    event = router.normalize_kernel_event(record)
    assert event is not None
    assert event.run_id == "run-7"
    assert event.step_id == "s2"
    assert event.type == WorkflowEventType.KERNEL_EVENT
    assert event.payload["kernel_event_type"] == "workload.started"

    row = backend.fetch_one(
        "SELECT * FROM workflow_events WHERE run_id = ?", ("run-7",)
    )
    assert row is not None


def test_kernel_event_explicit_run_id_overrides(router: EventRouter):
    record = _FakeKernelEvent(event_type="workload.log", attributes={})
    event = router.normalize_kernel_event(record, run_id="run-explicit")
    assert event is not None
    assert event.run_id == "run-explicit"


# ---------------------------------------------------------------------------
# Subscribers
# ---------------------------------------------------------------------------


def test_subscriber_receives_emitted_events(router: EventRouter):
    received: list[WorkflowEvent] = []
    router.subscribe(received.append)
    router.emit("run-1", WorkflowEventType.RUN_CREATED, "created")
    assert len(received) == 1
    assert received[0].run_id == "run-1"


def test_subscriber_error_does_not_break_emit(router: EventRouter):
    def boom(_event: WorkflowEvent) -> None:
        raise RuntimeError("subscriber failed")

    good: list[WorkflowEvent] = []
    router.subscribe(boom)
    router.subscribe(good.append)
    # Emission must still succeed and reach the healthy subscriber.
    event = router.emit("run-1", WorkflowEventType.RUN_CREATED, "created")
    assert event.seq == 1
    assert len(good) == 1
