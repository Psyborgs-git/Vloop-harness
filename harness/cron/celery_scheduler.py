"""Celery-based scheduler.

This acts as an adapter to push tasks into a Celery Beat backend.
Note: For a full distributed celery setup, celery beat needs to read from
a dynamic source (like django-celery-beat or redis). Here we implement a simplified
Redis-based adapter where we dynamically update beat schedule.
"""

from __future__ import annotations

import structlog

from harness.cron.base import BaseScheduler
from harness.data.models import CronJob
from harness.settings import HarnessSettings

logger = structlog.get_logger(__name__)


class CeleryScheduler(BaseScheduler):
    """Adapter for a Celery Beat scheduler."""

    def __init__(self) -> None:
        self.settings = HarnessSettings()  # type: ignore[call-arg]
        # In a real celery-beat implementation dynamically adding jobs at runtime
        # often involves writing to a database (like django-celery-beat) or RedBeat.
        # We simulate the interface here but require an external celery beat process.

        # We lazy load celery to avoid hard dependency issues on boot if not used
        try:
            from celery import Celery
            # We assume redis is used as broker
            self.celery_app = Celery('vloop_cron', broker='redis://localhost:6379/0')
        except ImportError:
            self.celery_app = None
            logger.warning("celery_not_installed")

    async def start(self) -> None:
        """Start the scheduler (no-op in adapter, celery beat runs externally)."""
        logger.info("celery_scheduler_adapter_started")

    async def stop(self) -> None:
        """Stop the scheduler."""
        logger.info("celery_scheduler_adapter_stopped")

    async def add_job(self, job: CronJob) -> None:
        """Register a job."""
        if not self.celery_app:
            return

        # Example interface for RedBeat or similar dynamic celery beat schedulers.
        # This is a stub for the architecture - actual implementation depends on
        # the specific celery-beat scheduler backend (e.g. redbeat).
        logger.info("celery_scheduler_job_added", job_id=job.id)

    async def remove_job(self, job_id: str) -> None:
        """Unregister a job."""
        if not self.celery_app:
            return

        logger.info("celery_scheduler_job_removed", job_id=job_id)
