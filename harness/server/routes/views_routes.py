"""REST routes for AI-generated React view stubs.

Endpoints
─────────
  POST   /api/views/generate  — generate a React TSX stub from a description
  GET    /api/views            — list all generated views
  DELETE /api/views/{id}       — delete a view record (optionally remove files)
"""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from harness.data.db import get_session
from harness.data.models import GeneratedView
from harness.data.repository import Repository
from harness.server.routes.view_validation import (
    validate_component_name,
    validate_react_code,
    write_view_stub,
)

router = APIRouter(prefix="/api/views", tags=["views"])


# ── Request / Response models ─────────────────────────────────────────────────


class GenerateViewRequest(BaseModel):
    description: str
    component_name: str = ""
    spec: str = ""
    session_id: str | None = None


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post("/generate", status_code=201)
async def generate_view(
    body: GenerateViewRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    mp = request.app.state.main_process
    storage = request.app.state.vloop_storage

    if not mp.ai.is_ready:
        raise HTTPException(status_code=503, detail="AI engine not configured")

    # Resolve available components for context
    repo = Repository(db)
    components = await repo.list_components()
    available_comps = json.dumps(
        [{"id": c.id, "name": c.name, "description": c.description} for c in components]
    )

    # Call the ViewGenerator DSPy module
    try:
        prediction = await mp.ai.generate_view(
            ui_description=body.description,
            available_components=available_comps,
            spec=body.spec,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AI generation failed: {exc}") from exc

    react_code: str = getattr(prediction, "react_code", "") or ""
    raw_name: str = body.component_name or getattr(prediction, "component_name", "") or ""
    view_spec: str = getattr(prediction, "view_spec", "") or ""

    # Validate component name
    try:
        component_name = validate_component_name(raw_name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Validate react code safety
    try:
        validate_react_code(react_code)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Write stub files to disk (react/src/components/generated/{component_name}/)
    react_root = storage.project_dir.parent / "react" / "src" / "components" / "generated"
    file_path = write_view_stub(react_root, component_name, react_code)

    # Persist to DB
    view = GeneratedView(
        id=str(uuid.uuid4()),
        name=body.description[:255],
        component_name=component_name,
        react_code=react_code,
        view_spec=view_spec,
        file_path=file_path,
        session_id=body.session_id,
    )
    view = await repo.save_view(view)

    return _view_to_dict(view)


@router.get("")
async def list_views(
    db: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    repo = Repository(db)
    views = await repo.list_views()
    return [_view_to_dict(v) for v in views]


@router.delete("/{view_id}", status_code=204)
async def delete_view(
    view_id: str,
    db: AsyncSession = Depends(get_session),
) -> None:
    repo = Repository(db)
    view = await repo.get_view(view_id)
    if not view:
        raise HTTPException(status_code=404, detail="View not found")
    # Remove the whole generated component directory (App.tsx + main.tsx, etc.)
    if view.file_path:
        try:
            p = Path(view.file_path)
            comp_dir = p.parent
            if comp_dir.exists():
                shutil.rmtree(comp_dir, ignore_errors=True)
            elif p.exists():
                p.unlink()
        except Exception:
            pass
    await repo.delete_view(view_id)


# ── Serialisation helpers ─────────────────────────────────────────────────────


def _view_to_dict(v: GeneratedView) -> dict[str, Any]:
    return {
        "id": v.id,
        "name": v.name,
        "component_name": v.component_name,
        "react_code": v.react_code,
        "view_spec": v.view_spec,
        "file_path": v.file_path,
        "session_id": v.session_id,
        "created_at": v.created_at.isoformat(),
    }

