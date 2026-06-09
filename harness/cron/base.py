"""Base interface for cron schedulers."""

from __future__ import annotations

import abc

from harness.data.models import CronJob


class BaseScheduler(abc.ABC):
    """Abstract interface for a scheduled job manager."""

    @abc.abstractmethod
    async def start(self) -> None:
        """Start the scheduler engine."""
        pass

    @abc.abstractmethod
    async def stop(self) -> None:
        """Stop the scheduler engine."""
        pass

    @abc.abstractmethod
    async def add_job(self, job: CronJob) -> None:
        """Register a job with the scheduler.

        If the job already exists, this should update it.
        """
        pass

    @abc.abstractmethod
    async def remove_job(self, job_id: str) -> None:
        """Unregister a job from the scheduler."""
        pass
