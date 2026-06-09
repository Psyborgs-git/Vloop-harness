import pytest
from harness.cron.asyncio_scheduler import AsyncioScheduler
from harness.data.models import CronJob

@pytest.mark.asyncio
async def test_asyncio_scheduler_add_remove():
    scheduler = AsyncioScheduler()

    # Create a job
    job = CronJob(
        id="test-1",
        name="Test Job",
        cron_expression="* * * * *",
        target="webhook",
        target_url="http://localhost:8000/webhook",
        is_active=True
    )

    await scheduler.add_job(job)
    assert len(scheduler.jobs) == 1
    assert "test-1" in scheduler.jobs

    # Update job (same id)
    job.name = "Updated Job"
    await scheduler.add_job(job)
    assert len(scheduler.jobs) == 1
    assert scheduler.jobs["test-1"].name == "Updated Job"

    # Remove job
    await scheduler.remove_job("test-1")
    assert len(scheduler.jobs) == 0
