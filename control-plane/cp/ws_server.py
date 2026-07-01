"""WebSocket server — push channel for normalized workflow events.

The Frontend historically polls Control_Plane HTTP APIs for state. This module
adds the live push channel described in the design ("Event_Router + WebSocket
server"): a :class:`WebSocketServer` that runs alongside the threaded
:class:`cp.http_server.HttpShellServer` and streams normalized
:class:`~core.event_router.WorkflowEvent` objects to connected Frontend clients
(step transitions, approval-required, budget/rate status — Req 4.1, 7.5, 8.2,
20.4).

Design notes:

* **Standard library only.** The project avoids heavy dependencies, so this is a
  minimal WebSocket framing implementation over ``socket``/``threading`` rather
  than an external WS library. It matches the threaded lifecycle style of
  ``HttpShellServer`` (background thread + readiness event + ``start``/``stop``).
* **Event_Router is the integration point.** The transport never talks to the
  orchestrator directly. A thread-safe :class:`WorkflowEventBroadcaster`
  subscribes to an :class:`~core.event_router.EventRouter` and fans every
  emitted event (serialized via ``WorkflowEvent.to_dict()``) out to every
  connected client. The broadcaster is transport-agnostic: clients are any
  object exposing ``send(message: str)`` / ``close()``, which keeps it unit
  testable without a real network (see ``tests/test_ws_server.py``).
* **Non-blocking fan-out.** Each real connection owns a bounded outbound queue
  drained by its own writer thread, so a single slow Frontend client cannot
  stall event emission for the rest of the system.

End-to-end WebSocket delivery is exercised by task 30.11; bootstrap wiring of the
server into the runtime is task 30.10. This module provides the server and the
Event_Router push integration only.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import queue
import socket
import struct
import threading
from typing import Callable, Protocol, runtime_checkable

from core.event_router import EventRouter, WorkflowEvent

LOGGER = logging.getLogger("vloop.control_plane.ws")

# RFC 6455 magic GUID used to derive the Sec-WebSocket-Accept response value.
_WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

# Bound on a single client's outbound queue. A client that cannot keep up past
# this many buffered events is considered too slow and is dropped rather than
# allowed to grow memory without limit.
_DEFAULT_CLIENT_QUEUE_SIZE = 1000


@runtime_checkable
class WorkflowEventClient(Protocol):
    """A connected client able to receive serialized workflow events.

    The broadcaster only depends on this minimal surface, so production WebSocket
    connections and test fakes are interchangeable.
    """

    def send(self, message: str) -> None:  # pragma: no cover - protocol
        ...

    def close(self) -> None:  # pragma: no cover - protocol
        ...


class WorkflowEventBroadcaster:
    """Thread-safe fan-out of workflow events to connected clients.

    This is the integration seam between the :class:`EventRouter` and any
    transport. Call :meth:`subscribe_to` to wire it to an Event_Router; every
    emitted :class:`WorkflowEvent` is serialized with ``to_dict()`` and pushed to
    each registered client. Clients whose ``send`` raises are dropped so one bad
    connection cannot break delivery to the others.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._clients: set[WorkflowEventClient] = set()
        self._subscribed = False

    # -- client registry ----------------------------------------------------

    def register(self, client: WorkflowEventClient) -> None:
        """Add a client to receive future broadcast events."""
        with self._lock:
            self._clients.add(client)
        LOGGER.debug("workflow event client registered (%d total)", self.client_count)

    def unregister(self, client: WorkflowEventClient) -> None:
        """Stop sending events to a client (idempotent)."""
        with self._lock:
            self._clients.discard(client)
        LOGGER.debug("workflow event client removed (%d total)", self.client_count)

    @property
    def client_count(self) -> int:
        with self._lock:
            return len(self._clients)

    # -- Event_Router integration -------------------------------------------

    def subscribe_to(self, event_router: EventRouter) -> None:
        """Subscribe this broadcaster to an Event_Router (the integration point).

        Idempotent per broadcaster: subscribing twice would double-deliver, so a
        repeat call is ignored.
        """
        with self._lock:
            if self._subscribed:
                return
            self._subscribed = True
        event_router.subscribe(self.broadcast)

    # -- fan-out ------------------------------------------------------------

    def broadcast(self, event: WorkflowEvent) -> None:
        """Serialize and push one event to every connected client.

        A failing client is removed and never interrupts delivery to the others.
        """
        message = self.encode(event)
        with self._lock:
            clients = tuple(self._clients)

        dead: list[WorkflowEventClient] = []
        for client in clients:
            try:
                client.send(message)
            except Exception:  # noqa: BLE001 - a bad client must not break others
                LOGGER.warning("dropping workflow event client after send failure")
                dead.append(client)

        if dead:
            with self._lock:
                for client in dead:
                    self._clients.discard(client)
            for client in dead:
                _safe_close(client)

    @staticmethod
    def encode(event: WorkflowEvent) -> str:
        """Serialize a workflow event to the JSON wire form the Frontend reads."""
        return json.dumps(event.to_dict(), separators=(",", ":"), sort_keys=True)


class WebSocketServer:
    """Threaded WebSocket server that runs alongside ``HttpShellServer``.

    Lifecycle mirrors ``HttpShellServer``: :meth:`start` spawns a daemon accept
    thread and blocks until the listener is ready (or surfaces a startup error);
    :meth:`stop` closes the listener, drops all clients, and joins the thread.
    """

    def __init__(
        self,
        host: str,
        port: int,
        broadcaster: WorkflowEventBroadcaster | None = None,
        *,
        client_queue_size: int = _DEFAULT_CLIENT_QUEUE_SIZE,
    ) -> None:
        self.host = host
        self.port = port
        self.broadcaster = broadcaster or WorkflowEventBroadcaster()
        self._client_queue_size = client_queue_size
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._startup_error: RuntimeError | None = None
        self._stopping = threading.Event()
        self._connections: set[_WebSocketConnection] = set()
        self._conn_lock = threading.RLock()

    @property
    def bound_port(self) -> int:
        """The actual listening port (useful when constructed with port 0)."""
        if self._sock is None:
            return self.port
        return self._sock.getsockname()[1]

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._stopping.clear()
        self._ready.clear()
        self._thread = threading.Thread(
            target=self._serve,
            name="vloop-control-plane-ws",
            daemon=True,
        )
        self._thread.start()

        if not self._ready.wait(timeout=10):
            raise RuntimeError("timed out while starting the control-plane WebSocket server")
        if self._startup_error is not None:
            raise self._startup_error

    def stop(self) -> None:
        self._stopping.set()
        sock = self._sock
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        with self._conn_lock:
            connections = tuple(self._connections)
        for connection in connections:
            connection.close()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=5)

    # -- accept loop --------------------------------------------------------

    def _serve(self) -> None:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.host, self.port))
            sock.listen(64)
            sock.settimeout(0.25)
            self._sock = sock
            self._ready.set()
            LOGGER.info("control-plane WebSocket server listening on %s:%s", self.host, self.bound_port)
        except Exception as exc:  # noqa: BLE001
            self._startup_error = RuntimeError(
                f"failed to start control-plane WebSocket server: {exc}"
            )
            self._ready.set()
            return

        while not self._stopping.is_set():
            try:
                client_sock, _addr = sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(
                target=self._handle_client,
                args=(client_sock,),
                name="vloop-ws-client",
                daemon=True,
            ).start()

    def _handle_client(self, client_sock: socket.socket) -> None:
        try:
            if not _perform_handshake(client_sock):
                client_sock.close()
                return
        except OSError:
            client_sock.close()
            return

        connection = _WebSocketConnection(client_sock, max_queue=self._client_queue_size)
        with self._conn_lock:
            self._connections.add(connection)
        self.broadcaster.register(connection)
        connection.start()

        # Block until the client disconnects, then clean up registrations.
        connection.wait_closed()
        self.broadcaster.unregister(connection)
        with self._conn_lock:
            self._connections.discard(connection)


class _WebSocketConnection:
    """A single accepted WebSocket connection with a bounded outbound queue.

    Events are enqueued by :meth:`send` (called from the broadcaster) and drained
    by a dedicated writer thread, so broadcasting never blocks on socket I/O. A
    small reader thread watches for client-initiated close/disconnect.
    """

    def __init__(self, sock: socket.socket, *, max_queue: int) -> None:
        self._sock = sock
        self._queue: queue.Queue[str | None] = queue.Queue(maxsize=max_queue)
        self._closed = threading.Event()
        self._writer: threading.Thread | None = None
        self._reader: threading.Thread | None = None

    def start(self) -> None:
        self._writer = threading.Thread(
            target=self._write_loop, name="vloop-ws-writer", daemon=True
        )
        self._reader = threading.Thread(
            target=self._read_loop, name="vloop-ws-reader", daemon=True
        )
        self._writer.start()
        self._reader.start()

    def send(self, message: str) -> None:
        """Queue a text message for delivery (non-blocking).

        Raises if the connection is closed or the client is too slow (queue
        full), which signals the broadcaster to drop this client.
        """
        if self._closed.is_set():
            raise ConnectionError("websocket connection is closed")
        try:
            self._queue.put_nowait(message)
        except queue.Full as exc:
            raise ConnectionError("websocket client outbound queue is full") from exc

    def close(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        # Unblock the writer thread.
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        try:
            self._sock.close()
        except OSError:
            pass

    def wait_closed(self, timeout: float | None = None) -> bool:
        return self._closed.wait(timeout)

    # -- loops --------------------------------------------------------------

    def _write_loop(self) -> None:
        while not self._closed.is_set():
            try:
                message = self._queue.get(timeout=0.25)
            except queue.Empty:
                continue
            if message is None:
                break
            try:
                self._sock.sendall(encode_text_frame(message))
            except OSError:
                break
        self.close()

    def _read_loop(self) -> None:
        # We do not interpret inbound application data; we only need to detect a
        # client disconnect / close frame so we can tear down cleanly.
        while not self._closed.is_set():
            try:
                data = self._sock.recv(4096)
            except (socket.timeout, BlockingIOError):
                continue
            except OSError:
                break
            if not data:
                break
        self.close()


# ---------------------------------------------------------------------------
# WebSocket framing / handshake (RFC 6455, server side, unmasked frames)
# ---------------------------------------------------------------------------


def compute_accept_key(sec_websocket_key: str) -> str:
    """Derive the ``Sec-WebSocket-Accept`` header value from the client key."""
    digest = hashlib.sha1((sec_websocket_key + _WS_GUID).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def encode_text_frame(payload: str) -> bytes:
    """Encode a UTF-8 text message as a single unmasked WebSocket frame.

    Server-to-client frames MUST NOT be masked (RFC 6455 §5.1).
    """
    data = payload.encode("utf-8")
    length = len(data)
    header = bytearray()
    header.append(0x81)  # FIN=1, opcode=0x1 (text)
    if length < 126:
        header.append(length)
    elif length < 65536:
        header.append(126)
        header.extend(struct.pack(">H", length))
    else:
        header.append(127)
        header.extend(struct.pack(">Q", length))
    return bytes(header) + data


def _perform_handshake(sock: socket.socket) -> bool:
    """Read the client's HTTP upgrade request and reply with the 101 response.

    Returns ``True`` on a successful WebSocket handshake, ``False`` otherwise.
    """
    sock.settimeout(5.0)
    request = _read_http_request(sock)
    if request is None:
        return False

    headers = _parse_headers(request)
    upgrade = headers.get("upgrade", "").lower()
    key = headers.get("sec-websocket-key")
    if "websocket" not in upgrade or not key:
        _reject(sock)
        return False

    accept = compute_accept_key(key)
    response = (
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {accept}\r\n"
        "\r\n"
    )
    sock.sendall(response.encode("ascii"))
    # Switch to a short timeout so the reader loop can poll for disconnects.
    sock.settimeout(0.25)
    return True


def _read_http_request(sock: socket.socket, limit: int = 65536) -> str | None:
    buffer = bytearray()
    while b"\r\n\r\n" not in buffer:
        try:
            chunk = sock.recv(4096)
        except OSError:
            return None
        if not chunk:
            return None
        buffer.extend(chunk)
        if len(buffer) > limit:
            return None
    return buffer.decode("latin-1", errors="replace")


def _parse_headers(request: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    lines = request.split("\r\n")
    for line in lines[1:]:
        if not line or ":" not in line:
            continue
        name, _, value = line.partition(":")
        headers[name.strip().lower()] = value.strip()
    return headers


def _reject(sock: socket.socket) -> None:
    try:
        sock.sendall(
            b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n"
            b"expected a WebSocket upgrade request"
        )
    except OSError:
        pass


def _safe_close(client: WorkflowEventClient) -> None:
    close = getattr(client, "close", None)
    if callable(close):
        try:
            close()
        except Exception:  # noqa: BLE001
            LOGGER.debug("error while closing dropped client", exc_info=True)


def attach_to_event_router(
    event_router: EventRouter,
    broadcaster: WorkflowEventBroadcaster | None = None,
) -> WorkflowEventBroadcaster:
    """Convenience wiring: build/return a broadcaster subscribed to ``event_router``.

    Bootstrap (task 30.10) can call this to obtain the push channel and hand the
    same broadcaster to a :class:`WebSocketServer`.
    """
    broadcaster = broadcaster or WorkflowEventBroadcaster()
    broadcaster.subscribe_to(event_router)
    return broadcaster


__all__ = [
    "WebSocketServer",
    "WorkflowEventBroadcaster",
    "WorkflowEventClient",
    "attach_to_event_router",
    "compute_accept_key",
    "encode_text_frame",
]


# Re-exported for callers that want the broadcaster's callback type.
WorkflowEventCallback = Callable[[WorkflowEvent], None]
