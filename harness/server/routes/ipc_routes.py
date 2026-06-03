import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

router = APIRouter(prefix="/ipc", tags=["ipc"])
logger = logging.getLogger(__name__)

class RustPushPayload(BaseModel):
    channel: str
    payload: dict

@router.post("/rust_push")
async def rust_push(req: RustPushPayload):
    # This is the actual IPC integration receiving HTTP posts from Rust instead of websockets
    # The rust push sends things here (like HITL approvals from the kernel if needed, or system updates)
    logger.info(f"Received IPC push from Rust on channel {req.channel}: {req.payload}")
    return {"success": True}

@router.websocket("/rust_ws")
async def rust_ipc_ws(websocket: WebSocket):
    # Websocket version for bidirectional streaming
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            logger.info(f"Received IPC WS from Rust: {message}")
            if message.get("type") == "vault_request":
                # Simulated vault response
                await websocket.send_text(json.dumps({"type": "vault_response", "key": "test_key"}))
    except WebSocketDisconnect:
        logger.info("Rust IPC disconnected")
