"""WebSocket handler — /ws/{component_id} bidirectional event stream."""

from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/ws/{component_id}")
async def component_ws(component_id: str, ws: WebSocket) -> None:
    mp = ws.app.state.main_process
    comp = mp.get_component(component_id)

    if comp is None:
        await ws.close(code=4004, reason="Component not found")
        return

    await ws.accept()
    comp._add_ws(ws)
    mp.logger.get(component_id).info("WebSocket connected")

    # Send initial state immediately
    await ws.send_text(json.dumps({"type": "state_update", "data": comp.state}))

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
                event_name = msg.get("type", "event")
                payload = msg.get("data")
                await comp.on_event(event_name, payload)
            except json.JSONDecodeError:
                mp.logger.get(component_id).warn(f"Invalid WS message: {raw!r}")
    except WebSocketDisconnect:
        pass
    finally:
        comp._remove_ws(ws)
        mp.logger.get(component_id).info("WebSocket disconnected")
