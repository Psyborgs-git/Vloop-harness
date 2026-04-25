"""FastAPI routes for agent run management.

Endpoints
─────────
  POST   /api/agents/runs                  — start a new agent run
  GET    /api/agents/runs                  — list runs (latest first)
  GET    /api/agents/runs/{id}             — get run + steps
  POST   /api/agents/runs/{id}/cancel      — cancel a running/paused run
  POST   /api/agents/runs/{id}/resume      — resume a paused run
  DELETE /api/agents/runs/{id}             — delete a run record
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from harness.data.db import get_session
from harness.data.repository import Repository

router = APIRouter(prefix="/api/agents", tags=["agents"])


# ── Request / Response models ─────────────────────────────────────────────────


class StartRunRequest(BaseModel):
    goal: str
    session_id: str | None = None
    autonomy_mode: str = "suggest"
    context: str = ""


class ResumeRunRequest(BaseModel):
    confirmed_token: str | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────


def _mp(request: Request) -> Any:
    return request.app.state.main_process


def _run_to_dict(run: Any) -> dict[str, Any]:
    return {
        "id": run.id,
        "goal": run.goal,
        "plan": run.plan,
        "status": run.status,
        "autonomy_mode": run.autonomy_mode,
        "session_id": run.session_id,
        "result": run.result,
        "error": run.error,
        "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat(),
        "steps": [_step_to_dict(s) for s in (run.steps or [])],
    }


def _step_to_dict(step: Any) -> dict[str, Any]:
    return {
        "id": step.id,
        "run_id": step.run_id,
        "step_type": step.step_type,
        "tool_name": step.tool_name,
        "input_data": step.input_data,
        "output_data": step.output_data,
        "status": step.status,
        "error": step.error,
        "confirmation_token": step.confirmation_token,
        "duration_ms": step.duration_ms,
        "created_at": step.created_at.isoformat(),
    }


def _run_to_summary(run: Any) -> dict[str, Any]:
    """Return a run summary without step details."""
    return {
        "id": run.id,
        "goal": run.goal,
        "status": run.status,
        "autonomy_mode": run.autonomy_mode,
        "session_id": run.session_id,
        "error": run.error,
        "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat(),
    }


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post("/runs", status_code=201)
async def start_run(
    body: StartRunRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Start a new agent run.  Returns immediately with the run record."""
    from harness.engine.agent_runner import AgentOrchestrator

    orchestrator = AgentOrchestrator(main_process=_mp(request), db_session=db)
    run = await orchestrator.start(
        goal=body.goal,
        session_id=body.session_id,
        autonomy_mode=body.autonomy_mode,
        context=body.context,
    )
    return _run_to_summary(run)


@router.get("/runs")
async def list_runs(
    limit: int = 50,
    db: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    repo = Repository(db)
    runs = await repo.list_agent_runs(limit=limit)
    return [_run_to_summary(r) for r in runs]


@router.get("/runs/{run_id}")
async def get_run(
    run_id: str,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    repo = Repository(db)
    run = await repo.get_agent_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return _run_to_dict(run)


@router.post("/runs/{run_id}/cancel", status_code=200)
async def cancel_run(
    run_id: str,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    from harness.engine.agent_runner import AgentOrchestrator

    orchestrator = AgentOrchestrator(main_process=_mp(request), db_session=db)
    await orchestrator.cancel(run_id)
    return {"run_id": run_id, "status": "cancelled"}


@router.post("/runs/{run_id}/resume", status_code=200)
async def resume_run(
    run_id: str,
    body: ResumeRunRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    from harness.engine.agent_runner import AgentOrchestrator

    orchestrator = AgentOrchestrator(main_process=_mp(request), db_session=db)
    await orchestrator.resume(run_id, confirmed_token=body.confirmed_token)
    return {"run_id": run_id, "status": "resuming"}


@router.delete("/runs/{run_id}", status_code=204)
async def delete_run(
    run_id: str,
    db: AsyncSession = Depends(get_session),
) -> None:
    repo = Repository(db)
    await repo.delete_agent_run(run_id)
