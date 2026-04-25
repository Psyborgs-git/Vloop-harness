"""FastAPI routes for app manifest management.

An AppManifest links a backend (component or DSPy pipeline) to one or more
React views to form a first-class full-stack application.

Endpoints
─────────
  POST   /api/apps/manifests                      — create a manifest
  GET    /api/apps/manifests                      — list manifests (filter by ?status=)
  GET    /api/apps/manifests/{id}                 — get a specific manifest
  PUT    /api/apps/manifests/{id}                 — update a manifest
  POST   /api/apps/manifests/{id}/promote         — change status (draft→validated→active…)
  DELETE /api/apps/manifests/{id}                 — delete a manifest

  GET    /api/apps/traces                         — list tool traces
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from harness.data.db import get_session
from harness.data.repository import Repository

router = APIRouter(prefix="/api/apps", tags=["apps"])


# ── Request / Response models ─────────────────────────────────────────────────


class CreateManifestRequest(BaseModel):
    name: str
    description: str = ""
    backend_type: str = "pipeline"
    backend_id: str | None = None
    react_views: list[str] = []
    permissions: list[str] = []
    state_schema: dict[str, Any] = {}
    agent_run_id: str | None = None


class UpdateManifestRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    backend_type: str | None = None
    backend_id: str | None = None
    react_views: list[str] | None = None
    permissions: list[str] | None = None
    state_schema: dict[str, Any] | None = None


class PromoteRequest(BaseModel):
    status: str  # draft | validated | active | archived


# ── Helpers ───────────────────────────────────────────────────────────────────

_VALID_STATUSES = {"draft", "validated", "active", "archived"}


def _manifest_to_dict(m: Any) -> dict[str, Any]:
    return {
        "id": m.id,
        "name": m.name,
        "description": m.description,
        "backend_type": m.backend_type,
        "backend_id": m.backend_id,
        "react_views": m.react_views,
        "permissions": m.permissions,
        "state_schema": m.state_schema,
        "status": m.status,
        "agent_run_id": m.agent_run_id,
        "created_at": m.created_at.isoformat(),
        "updated_at": m.updated_at.isoformat(),
    }


def _trace_to_dict(t: Any) -> dict[str, Any]:
    return {
        "id": t.id,
        "tool_name": t.tool_name,
        "component_id": t.component_id,
        "session_id": t.session_id,
        "run_step_id": t.run_step_id,
        "inputs": t.inputs,
        "outputs": t.outputs,
        "risk_level": t.risk_level,
        "confirmation_token": t.confirmation_token,
        "duration_ms": t.duration_ms,
        "success": t.success,
        "created_at": t.created_at.isoformat(),
    }


# ── Manifest CRUD ─────────────────────────────────────────────────────────────


@router.post("/manifests", status_code=201)
async def create_manifest(
    body: CreateManifestRequest,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    repo = Repository(db)
    manifest = await repo.create_app_manifest(
        name=body.name,
        description=body.description,
        backend_type=body.backend_type,
        backend_id=body.backend_id,
        react_views=body.react_views,
        permissions=body.permissions,
        state_schema=body.state_schema,
        agent_run_id=body.agent_run_id,
    )
    return _manifest_to_dict(manifest)


@router.get("/manifests")
async def list_manifests(
    status: str | None = None,
    db: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    repo = Repository(db)
    manifests = await repo.list_app_manifests(status=status)
    return [_manifest_to_dict(m) for m in manifests]


@router.get("/manifests/{manifest_id}")
async def get_manifest(
    manifest_id: str,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    repo = Repository(db)
    manifest = await repo.get_app_manifest(manifest_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="App manifest not found")
    return _manifest_to_dict(manifest)


@router.put("/manifests/{manifest_id}")
async def update_manifest(
    manifest_id: str,
    body: UpdateManifestRequest,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    repo = Repository(db)
    manifest = await repo.get_app_manifest(manifest_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="App manifest not found")

    updates: dict[str, Any] = {}
    for field in ("name", "description", "backend_type", "backend_id",
                  "react_views", "permissions", "state_schema"):
        val = getattr(body, field, None)
        if val is not None:
            updates[field] = val

    if updates:
        await repo.update_app_manifest(manifest_id, **updates)
        manifest = await repo.get_app_manifest(manifest_id)
        if manifest is None:
            raise HTTPException(status_code=404, detail="App manifest not found")

    return _manifest_to_dict(manifest)


@router.post("/manifests/{manifest_id}/promote")
async def promote_manifest(
    manifest_id: str,
    body: PromoteRequest,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if body.status not in _VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status {body.status!r}. Must be one of: {sorted(_VALID_STATUSES)}",
        )
    repo = Repository(db)
    manifest = await repo.get_app_manifest(manifest_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="App manifest not found")

    await repo.update_app_manifest(manifest_id, status=body.status)
    manifest = await repo.get_app_manifest(manifest_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="App manifest not found")
    return _manifest_to_dict(manifest)


@router.delete("/manifests/{manifest_id}", status_code=204)
async def delete_manifest(
    manifest_id: str,
    db: AsyncSession = Depends(get_session),
) -> None:
    repo = Repository(db)
    await repo.delete_app_manifest(manifest_id)


# ── Tool traces ───────────────────────────────────────────────────────────────


@router.get("/traces")
async def list_traces(
    tool_name: str | None = None,
    session_id: str | None = None,
    run_step_id: str | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    repo = Repository(db)
    traces = await repo.list_tool_traces(
        tool_name=tool_name,
        session_id=session_id,
        run_step_id=run_step_id,
        limit=limit,
    )
    return [_trace_to_dict(t) for t in traces]
