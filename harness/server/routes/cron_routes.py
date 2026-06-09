"""FastAPI routes for cron jobs management.

Endpoints
─────────
  GET    /api/cron               — list all cron jobs
  POST   /api/cron               — create a new cron job
  GET    /api/cron/{id}          — get a specific cron job
  PUT    /api/cron/{id}          — update a cron job
  DELETE /api/cron/{id}          — delete a cron job
"""

from __future__ import annotations

from typing import Any, Literal

from croniter import croniter
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from harness.cron.base import BaseScheduler
from harness.data.db import get_session
from harness.data.repository import Repository

router = APIRouter(prefix="/api/cron", tags=["cron"])


# ── Request / Response models ─────────────────────────────────────────────────




class CronJobCreate(BaseModel):
    name: str
    cron_expression: str = Field(..., description="Cron format e.g. '* * * * *'")
    target: str = Field(..., description="'agent_run' or 'webhook'")
    target_url: str | None = None
    payload: dict[str, Any] | None = None
    is_active: bool = True

    @field_validator("cron_expression")
    @classmethod
    def validate_cron(cls, v: str) -> str:
        if not croniter.is_valid(v):
            raise ValueError("Invalid cron expression")
        return v

class CronJobUpdate(BaseModel):
    name: str | None = None
    cron_expression: str | None = None
    target: str | None = None
    target_url: str | None = None
    payload: dict[str, Any] | None = None
    is_active: bool | None = None

    @field_validator("cron_expression")
    @classmethod
    def validate_cron(cls, v: str | None) -> str | None:
        if v and not croniter.is_valid(v):
            raise ValueError("Invalid cron expression")
        return v


# ── Helpers ───────────────────────────────────────────────────────────────────


def _cronjob_to_dict(job: Any) -> dict[str, Any]:
    return {
        "id": job.id,
        "name": job.name,
        "cron_expression": job.cron_expression,
        "target": job.target,
        "target_url": job.target_url,
        "payload": job.payload,
        "is_active": job.is_active,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }


def _get_scheduler(request: Request) -> BaseScheduler:
    return request.app.state.scheduler


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("")
async def list_cron_jobs(
    active_only: bool = False,
    db: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    repo = Repository(db)
    jobs = await repo.list_cron_jobs(active_only=active_only)
    return [_cronjob_to_dict(j) for j in jobs]


@router.post("", status_code=201)
async def create_cron_job(
    body: CronJobCreate,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    repo = Repository(db)

    # Validate expression via scheduler or throw 400? We can leave to asyncio adapter.

    job = await repo.create_cron_job(
        name=body.name,
        cron_expression=body.cron_expression,
        target=body.target,
        target_url=body.target_url,
        payload=body.payload,
        is_active=body.is_active,
    )

    scheduler = _get_scheduler(request)
    await scheduler.add_job(job)

    return _cronjob_to_dict(job)


@router.get("/{job_id}")
async def get_cron_job(
    job_id: str,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    repo = Repository(db)
    job = await repo.get_cron_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Cron job not found")
    return _cronjob_to_dict(job)


@router.put("/{job_id}")
async def update_cron_job(
    job_id: str,
    body: CronJobUpdate,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    repo = Repository(db)

    update_data = body.model_dump(exclude_unset=True)
    job = await repo.update_cron_job(job_id, **update_data)

    if not job:
        raise HTTPException(status_code=404, detail="Cron job not found")

    scheduler = _get_scheduler(request)
    await scheduler.add_job(job)  # Adds/updates depending on adapter

    return _cronjob_to_dict(job)


@router.delete("/{job_id}", status_code=204)
async def delete_cron_job(
    job_id: str,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> None:
    repo = Repository(db)
    job = await repo.get_cron_job(job_id)
    if job:
        await repo.delete_cron_job(job_id)
        scheduler = _get_scheduler(request)
        await scheduler.remove_job(job_id)
