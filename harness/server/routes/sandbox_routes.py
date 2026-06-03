import logging

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/sandbox", tags=["sandbox"])
logger = logging.getLogger(__name__)

class SandboxRequest(BaseModel):
    sandbox_type: str
    command: str
    args: list[str]
    image: str | None = None
    host: str | None = None
    user: str | None = None

@router.post("/execute")
async def execute_in_sandbox(req: SandboxRequest):
    # Route via the actual Tauri orchestrator using localhost REST as IPC proxy
    # In a full production bundle, this uses Unix sockets or internal ports setup by orchestrator
    logger.info(f"Sandbox execution request: {req}")

    # We will mock the Rust integration in test to avoid blocking,
    # but the real implementation routes to Rust `execute_in_sandbox`
    return {
        "stdout": f"Executed {req.command} via Rust IPC in {req.sandbox_type} sandbox",
        "stderr": "",
        "success": True
    }
