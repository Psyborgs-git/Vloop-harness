"""REST routes for AI-generated React view stubs.

Endpoints
─────────
  POST   /api/views/generate  — generate a React TSX stub from a description
  GET    /api/views            — list all generated views
  DELETE /api/views/{id}       — delete a view record (optionally remove files)
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from harness.data.db import get_session
from harness.data.models import GeneratedView
from harness.data.repository import Repository

router = APIRouter(prefix="/api/views", tags=["views"])

# ── Validation ────────────────────────────────────────────────────────────────

_COMPONENT_NAME_RE = re.compile(r"^[A-Z][a-zA-Z0-9]{1,63}$")

# Patterns that must not appear in generated React code (security baseline)
_BANNED_PATTERNS = [
    r"require\s*\(\s*['\"]child_process",
    r"\beval\s*\(",
    r"\bexec\s*\(",
    r"process\.env",
    r"__dirname",
    r"__filename",
    r"require\s*\(\s*['\"]fs['\"]",
    r"require\s*\(\s*['\"]path['\"]",
]


def _validate_component_name(name: str) -> str:
    """Raise ValueError if name is not a safe PascalCase identifier."""
    clean = name.strip()
    if not _COMPONENT_NAME_RE.match(clean):
        raise ValueError(
            f"component_name must be PascalCase [A-Z][a-zA-Z0-9]{{1,63}}, got {clean!r}"
        )
    return clean


def _validate_react_code(code: str) -> None:
    """Raise ValueError if generated code contains dangerous patterns."""
    for pattern in _BANNED_PATTERNS:
        if re.search(pattern, code):
            raise ValueError(
                f"Generated code contains a disallowed pattern: {pattern!r}"
            )


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
        component_name = _validate_component_name(raw_name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Validate react code safety
    try:
        _validate_react_code(react_code)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Write stub files to disk (react/src/components/generated/{component_name}/)
    file_path: str | None = None
    react_root = storage.project_dir.parent / "react" / "src" / "components" / "generated"
    try:
        comp_dir = react_root / component_name
        comp_dir.mkdir(parents=True, exist_ok=True)
        app_tsx = comp_dir / "App.tsx"
        app_tsx.write_text(react_code, encoding="utf-8")
        # Write a minimal main.tsx entry point
        main_tsx = comp_dir / "main.tsx"
        if not main_tsx.exists():
            main_tsx.write_text(
                f'import React from "react";\n'
                f'import ReactDOM from "react-dom/client";\n'
                f'import {component_name} from "./App";\n\n'
                f'ReactDOM.createRoot(document.getElementById("root")!).render(\n'
                f'  <React.StrictMode>\n'
                f'    <{component_name} />\n'
                f'  </React.StrictMode>\n'
                f');\n',
                encoding="utf-8",
            )
        file_path = str(app_tsx)
    except Exception:
        pass  # File write failure is non-fatal; DB record still saved

    # Persist to DB
    view_id = str(uuid.uuid4())
    view = GeneratedView(
        id=view_id,
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
    # Optionally remove generated files
    if view.file_path:
        try:
            p = Path(view.file_path)
            if p.exists():
                p.unlink()
            # Remove directory if empty
            if p.parent.exists() and not any(p.parent.iterdir()):
                p.parent.rmdir()
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
