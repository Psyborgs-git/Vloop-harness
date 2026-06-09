"""Asyncio-based scheduler using croniter."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import structlog
from croniter import croniter

from harness.cron.base import BaseScheduler
from harness.cron.executor import execute_cron_job
from harness.data.models import CronJob

logger = structlog.get_logger(__name__)


class AsyncioScheduler(BaseScheduler):
    """A lightweight in-app scheduler using asyncio and croniter.

    This runs inside the FastAPI process. It keeps track of jobs in memory
    and runs a background loop to check for the next scheduled tasks.
    """

    def __init__(self) -> None:
        self.jobs: dict[str, CronJob] = {}
        self.job_next_run: dict[str, datetime] = {}
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._background_tasks: set[asyncio.Task[None]] = set()

    async def start(self) -> None:
        """Start the background scheduler task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("asyncio_scheduler_started")

    async def stop(self) -> None:
        """Stop the background scheduler task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        # Gracefully await any pending background tasks
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)

        logger.info("asyncio_scheduler_stopped")

    async def add_job(self, job: CronJob) -> None:
        """Register or update a job."""
        if not job.is_active:
            if job.id in self.jobs:
                await self.remove_job(job.id)
            return

        # Ensure valid cron format
        now = datetime.now(UTC)
        try:
            itr = croniter(job.cron_expression, now)
            next_run = itr.get_next(datetime)
        except Exception as e:
            logger.error("invalid_cron_expression", job_id=job.id, error=str(e))
            return

        self.jobs[job.id] = job
        self.job_next_run[job.id] = next_run
        logger.info("asyncio_scheduler_job_added", job_id=job.id, next_run=next_run.isoformat())

    async def remove_job(self, job_id: str) -> None:
        """Unregister a job."""
        if job_id in self.jobs:
            del self.jobs[job_id]
            self.job_next_run.pop(job_id, None)
            logger.info("asyncio_scheduler_job_removed", job_id=job_id)

    async def _run_loop(self) -> None:
        """Background loop evaluating jobs."""
        while self._running:
            now = datetime.now(UTC)

            # Use gather to fire off tasks without blocking the main loop
            tasks_to_run = []

            for job_id, job in self.jobs.items():
                if not job.is_active:
                    continue

                try:
                    next_run = self.job_next_run.get(job_id)
                    if next_run and now >= next_run:
                        # Time to execute!
                        tasks_to_run.append(
                            execute_cron_job(job.target, job.target_url, job.payload)
                        )

                        # Compute next run time
                        itr = croniter(job.cron_expression, now)
                        self.job_next_run[job_id] = itr.get_next(datetime)

                except Exception as e:
                    logger.error("cron_evaluation_failed", job_id=job.id, error=str(e))

            if tasks_to_run:
                for t in tasks_to_run:
                    # Create async tasks and keep a strong reference to prevent GC mid-execution
                    task = asyncio.create_task(t)
                    self._background_tasks.add(task)
                    task.add_done_callback(self._background_tasks.discard)

            # Sleep for a short interval to avoid missing minute boundaries
            # while not spinning the CPU. 10 seconds is reasonable for minute-level crons.
            await asyncio.sleep(10.0)
