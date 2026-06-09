"""Executor for cron jobs.

When a cron job triggers (via asyncio, celery, etc.), this executor
reads the CronJob target/payload and performs the execution logic.
For the Vloop Harness, we enforce all execution to go through HTTP requests
so that it re-uses the exact same code paths as API-triggered requests.
"""

from __future__ import annotations

from typing import Any

import httpx

from harness.settings import HarnessSettings


async def execute_cron_job(
    job_target: str,
    job_target_url: str | None,
    payload: dict[str, Any] | None,
) -> None:
    """Execute the job by sending an HTTP POST request.

    If `job_target` == 'webhook', it posts to `job_target_url`.
    If `job_target` == 'agent_run', it posts to our internal `api/agents/runs` endpoint.
    """
    settings = HarnessSettings()  # type: ignore[call-arg]

    target_url = job_target_url
    if job_target == "agent_run":
        # Build local URL to our own API
        port = settings.harness_port
        host = settings.harness_host
        target_url = f"http://{host}:{port}/api/agents/runs"

    if not target_url:
        return  # Nothing to do or invalid configuration

    # Prepare payload, defaults to empty dict
    data = payload or {}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(target_url, json=data)
            response.raise_for_status()
    except Exception as e:
        import structlog
        logger = structlog.get_logger()
        logger.error("cron_job_execution_failed", target_url=target_url, error=str(e))
