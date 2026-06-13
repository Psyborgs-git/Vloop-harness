import grpc
import asyncio
from typing import AsyncGenerator, Optional
import structlog

from .sandbox_pb2 import ProvisionRequest, SandboxConfig, TeardownRequest
from .sandbox_pb2_grpc import SandboxServiceStub
from .middleware.context_cleaner import ContextCleaner

logger = structlog.get_logger()

# Key mapping matrix for Phase 2
KEY_MATRIX = {
    "Ctrl+C": b'\x03',
    "Ctrl+D": b'\x04',
    "Ctrl+Z": b'\x1A',
    "Esc": b'\x1B',
    "Up Arrow": b'\x1B[A',
}

class SandboxClient:
    def __init__(self, target: str = "127.0.0.1:9102"):
        self.target = target
        self.channel: Optional[grpc.aio.Channel] = None
        self.stub: Optional[SandboxServiceStub] = None
        self.cleaner = ContextCleaner()

    async def connect(self):
        if not self.channel:
            self.channel = grpc.aio.insecure_channel(self.target)
            self.stub = SandboxServiceStub(self.channel)

    async def close(self):
        if self.channel:
            await self.channel.close()
            self.channel = None
            self.stub = None

    async def provision(self, session_id: str, sandbox_type: SandboxConfig.Type, command: str, args: list[str]) -> bool:
        await self.connect()
        config = SandboxConfig(
            type=sandbox_type,
            command=command,
            args=args,
        )
        req = ProvisionRequest(session_id=session_id, config=config)
        try:
            resp = await self.stub.Provision(req)
            return resp.success
        except grpc.RpcError as e:
            logger.error("Provision failed", error=str(e))
            return False

    async def teardown(self, session_id: str) -> bool:
        await self.connect()
        req = TeardownRequest(session_id=session_id)
        try:
            resp = await self.stub.Teardown(req)
            return resp.success
        except grpc.RpcError as e:
            logger.error("Teardown failed", error=str(e))
            return False


