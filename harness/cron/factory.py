"""Scheduler factory."""

from __future__ import annotations

from harness.cron.base import BaseScheduler
from harness.settings import HarnessSettings


def get_scheduler() -> BaseScheduler:
    """Instantiate the configured scheduler adapter."""
    settings = HarnessSettings()  # type: ignore[call-arg]

    if settings.cron_scheduler_backend == "celery":
        from harness.cron.celery_scheduler import CeleryScheduler
        return CeleryScheduler()

    # Default to asyncio
    from harness.cron.asyncio_scheduler import AsyncioScheduler
    return AsyncioScheduler()
