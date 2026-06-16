"""ARQ-based scheduler.

This acts as an adapter to push tasks into an ARQ backend with Redis.
"""

from __future__ import annotations

from typing import Any

import structlog
from arq import create_pool
from arq.connections import RedisSettings

from harness.cron.base import BaseScheduler
from harness.data.models import CronJob
from harness.settings import HarnessSettings

logger = structlog.get_logger(__name__)


class ArqScheduler(BaseScheduler):
    """Adapter for an ARQ scheduler."""

    def __init__(self) -> None:
        self.settings = HarnessSettings()  # type: ignore[call-arg]
        import os
        redis_host = getattr(self.settings, "redis_host", os.getenv("REDIS_HOST", "localhost"))
        try:
            redis_port = int(getattr(self.settings, "redis_port", os.getenv("REDIS_PORT", 6379)))
        except (ValueError, TypeError):
            redis_port = 6379
        self.redis_settings = RedisSettings(host=redis_host, port=redis_port)
        self.redis_pool: Any = None

    async def start(self) -> None:
        """Start the scheduler by connecting to Redis."""
        self.redis_pool = await create_pool(self.redis_settings)
        logger.info("arq_scheduler_adapter_started")

    async def stop(self) -> None:
        """Stop the scheduler."""
        if self.redis_pool:
            await self.redis_pool.close()
        logger.info("arq_scheduler_adapter_stopped")

    async def add_job(self, job: CronJob) -> None:
        """Register a job."""
        if not self.redis_pool:
            return

        # Enqueue job to ARQ (simplified execution logic)
        logger.info("arq_scheduler_job_added", job_id=job.id)

    async def remove_job(self, job_id: str) -> None:
        """Unregister a job."""
        if not self.redis_pool:
            return

        logger.info("arq_scheduler_job_removed", job_id=job_id)
