"""
WebSocket event publisher adapter for Chat Module.
Implements EventPublisherPort interface and manages active WebSocket connections.
"""

from __future__ import annotations

from typing import Callable, Any
from fastapi import WebSocket

from harness.modules.chat.domain.entities import MessageSentEvent, Message
from harness.modules.chat.ports.outbound import EventPublisherPort


class WebSocketChatPublisher(EventPublisherPort):
    def __init__(self) -> None:
        self._active_connections: dict[str, set[WebSocket]] = {}
        self._external_forwarders: list[Callable[[str, Message], Any]] = []

    def register_forwarder(self, forwarder: Callable[[str, Message], Any]) -> None:
        """Register an external adapter's forwarding function (e.g. Telegram forwarder)."""
        self._external_forwarders.append(forwarder)

    async def connect(self, channel_id: str, websocket: WebSocket) -> None:
        """Register a new WebSocket connection for a channel."""
        await websocket.accept()
        if channel_id not in self._active_connections:
            self._active_connections[channel_id] = set()
        self._active_connections[channel_id].add(websocket)

    def disconnect(self, channel_id: str, websocket: WebSocket) -> None:
        """Deregister an active WebSocket connection."""
        if channel_id in self._active_connections:
            self._active_connections[channel_id].discard(websocket)
            if not self._active_connections[channel_id]:
                del self._active_connections[channel_id]

    async def publish_message_sent(self, event: MessageSentEvent) -> None:
        """Broadcast message sent event to all connected WebSockets in the channel."""
        msg = event.message
        channel_id = msg.channel_id
        
        # 1. Broadcast via WebSockets
        if channel_id in self._active_connections:
            payload = {
                "type": "message_created",
                "data": {
                    "id": msg.id,
                    "channel_id": msg.channel_id,
                    "sender_id": msg.sender_id,
                    "sender_name": msg.sender_name,
                    "sender_type": msg.sender_type,
                    "content": msg.content,
                    "created_at": msg.created_at.isoformat()
                }
            }

            dead_sockets = set()
            for ws in self._active_connections[channel_id]:
                try:
                    await ws.send_json(payload)
                except Exception:
                    dead_sockets.add(ws)

            # Cleanup
            for ws in dead_sockets:
                self.disconnect(channel_id, ws)

        # 2. Forward to external adapters (e.g., Telegram, WhatsApp)
        # Prevent forwarding messages that already originated from that platform
        import asyncio
        for forwarder in self._external_forwarders:
            try:
                if asyncio.iscoroutinefunction(forwarder):
                    asyncio.create_task(forwarder(channel_id, msg))
                else:
                    forwarder(channel_id, msg)
            except Exception as e:
                print(f"Error in chat publisher forwarding to external adapter: {e}")


# Global singleton instance for injection
_chat_ws_publisher: WebSocketChatPublisher | None = None


def get_chat_ws_publisher() -> WebSocketChatPublisher:
    global _chat_ws_publisher
    if _chat_ws_publisher is None:
        _chat_ws_publisher = WebSocketChatPublisher()
    return _chat_ws_publisher
