"""Integration tests for WebSocket delivery and template instantiation (task 30.11).

Two end-to-end concerns are covered:

1. **End-to-end WebSocket event delivery (Req 4.1, 20.1).** A real
   :class:`~cp.ws_server.WebSocketServer` is stood up on an ephemeral loopback
   port. A plain ``socket`` client performs the RFC 6455 upgrade handshake
   (validated with :func:`~cp.ws_server.compute_accept_key`), and we assert that
   a :class:`~core.event_router.WorkflowEvent` emitted through the wired
   :class:`~core.event_router.EventRouter` arrives at the client as the
   normalized, JSON-serialized event over a real WebSocket text frame. Secret
   redaction is asserted on the delivered payload (Req 20.1 / 21.4).

2. **Template catalog instantiation (Req 20.2).** Using the ``OrchestrationMixin``
   harness pattern (a real file-backed ``create_database``), the template catalog
   is seeded and ``instantiate_workflow_template`` is exercised: a known template
   validates + persists a new Workflow (returns an id that appears in
   ``list_workflows()``), while an unknown template id raises ``KeyError``.

The socket tests use generous timeouts and never rely on Hypothesis deadlines.
"""

from __future__ import annotations

import json
import socket
import struct
import tempfile
import time
from pathlib import Path
from typing import Any

import pytest

from core.database import SQLiteBackend, create_database
from core.event_router import EventRouter, WorkflowEventType
from cp.orchestration import OrchestrationMixin
from cp.ws_server import (
    WebSocketServer,
    WorkflowEventBroadcaster,
    compute_accept_key,
)


# ---------------------------------------------------------------------------
# Client-side WebSocket helpers (RFC 6455, client performs masked handshake;
# server replies unmasked, which is what we decode below).
# ---------------------------------------------------------------------------

_CLIENT_KEY = "dGhlIHNhbXBsZSBub25jZQ=="  # RFC 6455 §1.3 sample nonce.


def _client_handshake(sock: socket.socket, host: str, port: int) -> None:
    """Send the HTTP upgrade request and validate the 101 response."""
    request = (
        f"GET /ws HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {_CLIENT_KEY}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n"
    )
    sock.sendall(request.encode("ascii"))

    response = bytearray()
    while b"\r\n\r\n" not in response:
        chunk = sock.recv(4096)
        if not chunk:
            raise AssertionError("server closed during handshake")
        response.extend(chunk)

    text = response.decode("latin-1")
    assert text.startswith("HTTP/1.1 101"), text
    expected_accept = compute_accept_key(_CLIENT_KEY)
    assert f"Sec-WebSocket-Accept: {expected_accept}" in text, text


def _recv_exact(sock: socket.socket, count: int) -> bytes:
    """Read exactly ``count`` bytes from the socket or fail."""
    buffer = bytearray()
    while len(buffer) < count:
        chunk = sock.recv(count - len(buffer))
        if not chunk:
            raise AssertionError("server closed before a full frame arrived")
        buffer.extend(chunk)
    return bytes(buffer)


def _recv_text_frame(sock: socket.socket) -> str:
    """Decode one unmasked server text frame (RFC 6455 §5)."""
    header = _recv_exact(sock, 2)
    fin_opcode = header[0]
    assert fin_opcode == 0x81, f"expected FIN+text frame, got {fin_opcode:#x}"

    second = header[1]
    masked = bool(second & 0x80)
    assert not masked, "server-to-client frames must not be masked"
    length = second & 0x7F
    if length == 126:
        length = struct.unpack(">H", _recv_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack(">Q", _recv_exact(sock, 8))[0]

    payload = _recv_exact(sock, length)
    return payload.decode("utf-8")


def _wait_for(predicate, timeout: float = 5.0) -> None:
    """Poll until ``predicate()`` is truthy or the timeout elapses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition was not met before timeout")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def router(tmp_path: Path) -> EventRouter:
    return EventRouter(SQLiteBackend(tmp_path / "ws-delivery.db"))


@pytest.fixture()
def ws_server(router: EventRouter):
    """A running WebSocketServer on an ephemeral port wired to ``router``."""
    broadcaster = WorkflowEventBroadcaster()
    broadcaster.subscribe_to(router)
    server = WebSocketServer("127.0.0.1", 0, broadcaster=broadcaster)
    server.start()
    try:
        yield server
    finally:
        server.stop()


# ---------------------------------------------------------------------------
# (1) End-to-end WebSocket event delivery (Req 4.1, 20.1)
# ---------------------------------------------------------------------------


def test_emitted_event_is_delivered_over_real_websocket(
    router: EventRouter, ws_server: WebSocketServer
):
    client = socket.create_connection(
        ("127.0.0.1", ws_server.bound_port), timeout=5.0
    )
    client.settimeout(5.0)
    try:
        _client_handshake(client, "127.0.0.1", ws_server.bound_port)

        # The server registers the connection with the broadcaster only after
        # the handshake completes; wait for it before emitting.
        _wait_for(lambda: ws_server.broadcaster.client_count >= 1)

        event = router.emit(
            "run-42",
            WorkflowEventType.STEP_STATE_CHANGED,
            "step started",
            step_id="s1",
            payload={"state": "running"},
        )

        delivered = json.loads(_recv_text_frame(client))
        # The delivered payload is exactly the normalized event.
        assert delivered == event.to_dict()
        assert delivered["run_id"] == "run-42"
        assert delivered["type"] == WorkflowEventType.STEP_STATE_CHANGED
        assert delivered["step_id"] == "s1"
        assert delivered["payload"] == {"state": "running"}
    finally:
        client.close()


def test_delivered_event_payload_is_secret_redacted(
    router: EventRouter, ws_server: WebSocketServer
):
    client = socket.create_connection(
        ("127.0.0.1", ws_server.bound_port), timeout=5.0
    )
    client.settimeout(5.0)
    try:
        _client_handshake(client, "127.0.0.1", ws_server.bound_port)
        _wait_for(lambda: ws_server.broadcaster.client_count >= 1)

        router.emit(
            "run-42",
            WorkflowEventType.BUDGET_STATUS,
            "provider configured",
            payload={"api_key": "sk-super-secret", "model": "gpt-4o"},
        )

        raw = _recv_text_frame(client)
        delivered = json.loads(raw)
        # The raw secret never reaches the wire (Req 20.1 / 21.4).
        assert "sk-super-secret" not in raw
        assert delivered["payload"]["api_key"] == "[REDACTED]"
        assert delivered["payload"]["model"] == "gpt-4o"
    finally:
        client.close()


def test_multiple_events_arrive_in_order(
    router: EventRouter, ws_server: WebSocketServer
):
    client = socket.create_connection(
        ("127.0.0.1", ws_server.bound_port), timeout=5.0
    )
    client.settimeout(5.0)
    try:
        _client_handshake(client, "127.0.0.1", ws_server.bound_port)
        _wait_for(lambda: ws_server.broadcaster.client_count >= 1)

        router.emit("run-7", WorkflowEventType.RUN_CREATED, "created")
        router.emit("run-7", WorkflowEventType.STEP_STATE_CHANGED, "running")
        router.emit("run-7", WorkflowEventType.RUN_COMPLETED, "done")

        types = [json.loads(_recv_text_frame(client))["type"] for _ in range(3)]
        assert types == [
            WorkflowEventType.RUN_CREATED,
            WorkflowEventType.STEP_STATE_CHANGED,
            WorkflowEventType.RUN_COMPLETED,
        ]
        # The per-run sequence is monotonic in delivery order.
        client.settimeout(2.0)
    finally:
        client.close()


# ---------------------------------------------------------------------------
# (2) Template catalog instantiation (Req 20.2)
# ---------------------------------------------------------------------------


class _Harness(OrchestrationMixin):
    """Minimal host for the OrchestrationMixin backed by a real database."""

    def __init__(self, db: Any) -> None:
        self.db = db
        self.agent_orchestrator = None
        self._init_orchestration()


def _make_harness(tmp_root: Path) -> _Harness:
    return _Harness(create_database(None, tmp_root))


def test_instantiate_template_persists_new_workflow():
    with tempfile.TemporaryDirectory() as d:
        rt = _make_harness(Path(d))
        # Seed the catalog with a valid (empty-steps) template definition.
        rt._workflow_templates = {
            "research": {
                "id": "research",
                "name": "Research",
                "definition": {"name": "Research Base", "steps": []},
            }
        }

        # The template is discoverable via the catalog accessors.
        assert [t["id"] for t in rt.list_workflow_templates()] == ["research"]
        assert rt.get_workflow_template("research")["name"] == "Research"

        # Instantiating validates + persists a new Workflow with an id, and the
        # caller's overrides take precedence over the template fields.
        workflow = rt.instantiate_workflow_template("research", {"name": "My Run"})
        assert workflow["id"]
        assert workflow["name"] == "My Run"

        listed = rt.list_workflows()
        assert [w["id"] for w in listed] == [workflow["id"]]
        assert rt.get_workflow(workflow["id"])["name"] == "My Run"


def test_instantiate_template_without_overrides_uses_template_definition():
    with tempfile.TemporaryDirectory() as d:
        rt = _make_harness(Path(d))
        rt._workflow_templates = {
            "blank": {
                "id": "blank",
                "definition": {"name": "Blank Template", "steps": []},
            }
        }

        workflow = rt.instantiate_workflow_template("blank", {})
        assert workflow["id"]
        assert workflow["name"] == "Blank Template"
        assert [w["id"] for w in rt.list_workflows()] == [workflow["id"]]


def test_instantiate_unknown_template_raises_key_error():
    with tempfile.TemporaryDirectory() as d:
        rt = _make_harness(Path(d))
        rt._workflow_templates = {}
        with pytest.raises(KeyError):
            rt.instantiate_workflow_template("nope", {})
        # No workflow is persisted on failure.
        assert rt.list_workflows() == []


def test_instantiate_invalid_template_raises_and_persists_nothing():
    with tempfile.TemporaryDirectory() as d:
        rt = _make_harness(Path(d))
        # A dependency cycle is rejected by the Planner (Req 1.4): the template
        # is found but instantiation fails validation, persisting nothing.
        rt._workflow_templates = {
            "cyclic": {
                "id": "cyclic",
                "definition": {
                    "name": "Cyclic",
                    "steps": [
                        {"id": "a", "type": "noop", "dependsOn": ["b"]},
                        {"id": "b", "type": "noop", "dependsOn": ["a"]},
                    ],
                },
            }
        }
        with pytest.raises(ValueError):
            rt.instantiate_workflow_template("cyclic", {})
        assert rt.list_workflows() == []
