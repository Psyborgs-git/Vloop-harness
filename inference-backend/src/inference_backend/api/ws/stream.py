"""WebSocket /stream endpoint for real-time agent step streaming."""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

_connections: list[WebSocket] = []


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_message(msg_type: str, payload: dict) -> str:
    return json.dumps({
        "type": msg_type,
        "id": str(uuid.uuid4()),
        "timestamp": _now(),
        "payload": payload,
    })


async def broadcast(msg_type: str, payload: dict) -> None:
    """Broadcast a typed message to all connected WebSocket clients."""
    msg = make_message(msg_type, payload)
    dead = []
    for ws in list(_connections):
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _connections.remove(ws)


@router.websocket("/stream")
async def stream_endpoint(websocket: WebSocket):
    await websocket.accept()
    _connections.append(websocket)
    try:
        while True:
            # Keep connection alive with a ping
            data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
            # Echo back any client pings
            if data == "ping":
                await websocket.send_text("pong")
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    finally:
        if websocket in _connections:
            _connections.remove(websocket)
