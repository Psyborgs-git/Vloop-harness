"""Unit tests for the WebSocket push channel (task 30.1).

Covers the Event_Router integration point: a :class:`WorkflowEventBroadcaster`
subscribed to a *real* :class:`EventRouter` fans every emitted
:class:`WorkflowEvent` out to connected clients as JSON (``to_dict()``), exactly
the step transitions, approval-required, and budget/rate status events the
Frontend consumes (Req 4.1, 7.5, 8.2, 20.4).

No real network is used: a fake client implementing the tiny
``send``/``close`` surface stands in for a connected Frontend WebSocket. The WS
framing/handshake helpers are unit-tested directly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.database import SQLiteBackend
from core.event_router import EventRouter, WorkflowEvent, WorkflowEventType
from cp.ws_server import (
    WorkflowEventBroadcaster,
    attach_to_event_router,
    compute_accept_key,
    encode_text_frame,
)


class FakeClient:
    """In-memory stand-in for a connected Frontend WebSocket client."""

    def __init__(self) -> None:
        self.messages: list[str] = []
        self.closed = False

    def send(self, message: str) -> None:
        self.messages.append(message)

    def close(self) -> None:
        self.closed = True


class BoomClient:
    """A client whose send always fails, to verify isolation/dropping."""

    def __init__(self) -> None:
        self.closed = False

    def send(self, message: str) -> None:
        raise ConnectionError("client gone")

    def close(self) -> None:
        self.closed = True


@pytest.fixture()
def backend(tmp_path: Path) -> SQLiteBackend:
    return SQLiteBackend(tmp_path / "ws-events-test.db")


@pytest.fixture()
def router(backend: SQLiteBackend) -> EventRouter:
    return EventRouter(backend)


# ---------------------------------------------------------------------------
# Event_Router integration (the wiring under test)
# ---------------------------------------------------------------------------


def test_subscribed_broadcaster_streams_emitted_events_to_client(router: EventRouter):
    broadcaster = WorkflowEventBroadcaster()
    broadcaster.subscribe_to(router)

    client = FakeClient()
    broadcaster.register(client)

    event = router.emit(
        "run-1",
        WorkflowEventType.STEP_STATE_CHANGED,
        "step started",
        step_id="s1",
        payload={"state": "running"},
    )

    assert len(client.messages) == 1
    decoded = json.loads(client.messages[0])
    assert decoded == event.to_dict()
    assert decoded["run_id"] == "run-1"
    assert decoded["type"] == WorkflowEventType.STEP_STATE_CHANGED
    assert decoded["step_id"] == "s1"
    assert decoded["payload"] == {"state": "running"}


def test_streams_approval_and_budget_and_rate_events(router: EventRouter):
    broadcaster = attach_to_event_router(router)
    client = FakeClient()
    broadcaster.register(client)

    router.emit("run-1", WorkflowEventType.APPROVAL_REQUIRED, "approval needed")
    router.emit("run-1", WorkflowEventType.BUDGET_STATUS, "budget at 80%")
    router.emit("run-1", WorkflowEventType.RATE_LIMIT_STATUS, "rate limited")

    types = [json.loads(m)["type"] for m in client.messages]
    assert types == [
        WorkflowEventType.APPROVAL_REQUIRED,
        WorkflowEventType.BUDGET_STATUS,
        WorkflowEventType.RATE_LIMIT_STATUS,
    ]


def test_broadcasts_to_all_registered_clients(router: EventRouter):
    broadcaster = attach_to_event_router(router)
    a, b = FakeClient(), FakeClient()
    broadcaster.register(a)
    broadcaster.register(b)

    router.emit("run-1", WorkflowEventType.RUN_CREATED, "created")

    assert len(a.messages) == 1
    assert len(b.messages) == 1


def test_unregistered_client_stops_receiving(router: EventRouter):
    broadcaster = attach_to_event_router(router)
    client = FakeClient()
    broadcaster.register(client)
    router.emit("run-1", WorkflowEventType.RUN_CREATED, "created")

    broadcaster.unregister(client)
    router.emit("run-1", WorkflowEventType.RUN_COMPLETED, "done")

    assert len(client.messages) == 1


def test_failing_client_is_dropped_and_others_unaffected(router: EventRouter):
    broadcaster = attach_to_event_router(router)
    boom = BoomClient()
    good = FakeClient()
    broadcaster.register(boom)
    broadcaster.register(good)

    router.emit("run-1", WorkflowEventType.RUN_CREATED, "created")

    # The good client still received the event despite the failing one.
    assert len(good.messages) == 1
    # The failing client was removed and closed.
    assert broadcaster.client_count == 1
    assert boom.closed is True

    # A subsequent emit only reaches the good client.
    router.emit("run-1", WorkflowEventType.RUN_COMPLETED, "done")
    assert len(good.messages) == 2


def test_subscribe_to_is_idempotent(router: EventRouter):
    broadcaster = WorkflowEventBroadcaster()
    broadcaster.subscribe_to(router)
    broadcaster.subscribe_to(router)  # second call must not double-deliver

    client = FakeClient()
    broadcaster.register(client)
    router.emit("run-1", WorkflowEventType.RUN_CREATED, "created")

    assert len(client.messages) == 1


def test_emitted_payload_is_secret_redacted_before_broadcast(router: EventRouter):
    broadcaster = attach_to_event_router(router)
    client = FakeClient()
    broadcaster.register(client)

    router.emit(
        "run-1",
        WorkflowEventType.BUDGET_STATUS,
        "provider configured",
        payload={"api_key": "sk-secret", "model": "gpt-4o"},
    )

    decoded = json.loads(client.messages[0])
    assert "sk-secret" not in client.messages[0]
    assert decoded["payload"]["api_key"] == "[REDACTED]"
    assert decoded["payload"]["model"] == "gpt-4o"


def test_broadcast_encode_matches_to_dict():
    event = WorkflowEvent(
        run_id="run-1",
        seq=3,
        type=WorkflowEventType.STEP_STATE_CHANGED,
        message="m",
        step_id="s1",
        payload={"k": "v"},
        created_at="2024-01-01T00:00:00Z",
    )
    encoded = WorkflowEventBroadcaster.encode(event)
    assert json.loads(encoded) == event.to_dict()


# ---------------------------------------------------------------------------
# WebSocket framing / handshake helpers (RFC 6455)
# ---------------------------------------------------------------------------


def test_compute_accept_key_matches_rfc6455_example():
    # Example from RFC 6455 §1.3.
    assert (
        compute_accept_key("dGhlIHNhbXBsZSBub25jZQ==")
        == "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="
    )


def test_encode_text_frame_short_payload():
    frame = encode_text_frame("hi")
    assert frame[0] == 0x81  # FIN + text opcode
    assert frame[1] == 2  # unmasked, length 2
    assert frame[2:] == b"hi"


def test_encode_text_frame_medium_payload_uses_extended_length():
    payload = "x" * 200
    frame = encode_text_frame(payload)
    assert frame[0] == 0x81
    assert frame[1] == 126  # 16-bit extended length marker
    assert int.from_bytes(frame[2:4], "big") == 200
    assert frame[4:] == payload.encode("utf-8")


def test_encode_text_frame_large_payload_uses_64bit_length():
    payload = "y" * 70000
    frame = encode_text_frame(payload)
    assert frame[0] == 0x81
    assert frame[1] == 127  # 64-bit extended length marker
    assert int.from_bytes(frame[2:10], "big") == 70000
