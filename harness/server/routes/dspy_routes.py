"""REST routes for DSPy component and pipeline management.

Endpoints
─────────
  GET  /api/dspy/components              — list all component definitions
  POST /api/dspy/components              — create/save a component definition
  GET  /api/dspy/components/{id}         — get a single component
  PUT  /api/dspy/components/{id}         — update a component
  DELETE /api/dspy/components/{id}       — delete a component
  POST /api/dspy/components/{id}/run     — run a component with given inputs

  GET  /api/dspy/pipelines               — list all pipeline definitions
  POST /api/dspy/pipelines               — create a pipeline
  GET  /api/dspy/pipelines/{id}          — get a pipeline
  PUT  /api/dspy/pipelines/{id}          — update a pipeline
  DELETE /api/dspy/pipelines/{id}        — delete a pipeline
  POST /api/dspy/pipelines/{id}/run      — execute a pipeline
"""

from __future__ import annotations

import asyncio
import functools
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from harness.data.db import get_session
from harness.data.models import DSPyComponentDef, PipelineDef
from harness.data.repository import Repository
from harness.engine.component_registry import ComponentCompileError

router = APIRouter(prefix="/api/dspy", tags=["dspy"])


# ── Request / Response models ─────────────────────────────────────────────────


class ComponentCreateRequest(BaseModel):
    name: str
    description: str = ""
    code: str
    module_type: str = "ChainOfThought"


class ComponentUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    code: str | None = None
    module_type: str | None = None
    is_active: bool | None = None


class CloneComponentRequest(BaseModel):
    name: str


class RunInputsRequest(BaseModel):
    inputs: dict[str, Any] = {}


class PipelineCreateRequest(BaseModel):
    name: str
    description: str = ""
    steps: list[dict[str, Any]] = []  # [{component_id, config: {input_map}}]


class PipelineUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    steps: list[dict[str, Any]] | None = None
    is_active: bool | None = None


# ── Dependency helpers ────────────────────────────────────────────────────────


def _registry(request: Request):
    return request.app.state.component_registry


def _pipeline_builder(request: Request):
    return request.app.state.pipeline_builder


# ── Component endpoints ───────────────────────────────────────────────────────


@router.get("/components")
async def list_components(
    db: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    repo = Repository(db)
    comps = await repo.list_components()
    return [_component_to_dict(c) for c in comps]


@router.post("/components", status_code=201)
async def create_component(
    body: ComponentCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    registry = _registry(request)

    from harness.engine.component_registry import DSPyComponentRegistry

    sig_fields = DSPyComponentRegistry.extract_signature_fields(body.code)

    comp = DSPyComponentDef(
        id=f"comp_{uuid.uuid4().hex[:10]}",
        name=body.name,
        description=body.description,
        code=body.code,
        module_type=body.module_type,
        signature_fields=sig_fields,
    )

    # Try to compile immediately — surface errors early
    try:
        registry.compile(comp)
    except ComponentCompileError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    repo = Repository(db)
    saved = await repo.save_component(comp)
    return _component_to_dict(saved)


@router.get("/components/{component_id}")
async def get_component(
    component_id: str,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    repo = Repository(db)
    comp = await repo.get_component(component_id)
    if not comp:
        raise HTTPException(status_code=404, detail="Component not found")
    return _component_to_dict(comp)


@router.put("/components/{component_id}")
async def update_component(
    component_id: str,
    body: ComponentUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    repo = Repository(db)
    comp = await repo.get_component(component_id)
    if not comp:
        raise HTTPException(status_code=404, detail="Component not found")

    if body.name is not None:
        comp.name = body.name
    if body.description is not None:
        comp.description = body.description
    if body.module_type is not None:
        comp.module_type = body.module_type
    if body.is_active is not None:
        comp.is_active = body.is_active
    if body.code is not None:
        comp.code = body.code
        from harness.engine.component_registry import DSPyComponentRegistry

        comp.signature_fields = DSPyComponentRegistry.extract_signature_fields(body.code)
        registry = _registry(request)
        try:
            registry.compile(comp)
        except ComponentCompileError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    saved = await repo.save_component(comp)
    return _component_to_dict(saved)


@router.delete("/components/{component_id}", status_code=204)
async def delete_component(
    component_id: str,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> None:
    repo = Repository(db)
    comp = await repo.get_component(component_id)
    if not comp:
        raise HTTPException(status_code=404, detail="Component not found")
    _registry(request).unload(component_id)
    await repo.delete_component(component_id)


@router.post("/components/{component_id}/activate")
async def activate_component(
    component_id: str,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Activate a component by setting is_active=True and compiling it."""
    repo = Repository(db)
    comp = await repo.get_component(component_id)
    if not comp:
        raise HTTPException(status_code=404, detail="Component not found")

    comp.is_active = True
    registry = _registry(request)

    try:
        registry.compile(comp)
    except ComponentCompileError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    saved = await repo.save_component(comp)
    return {
        "component_id": saved.id,
        "status": "active",
    }


@router.post("/components/{component_id}/clone")
async def clone_component(
    component_id: str,
    body: CloneComponentRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Clone a component with a new name."""
    repo = Repository(db)
    comp = await repo.get_component(component_id)
    if not comp:
        raise HTTPException(status_code=404, detail="Component not found")

    # Create a new component with the same code but different name
    new_comp = await repo.create_dspy_component(
        name=body.name,
        description=f"Cloned from {comp.name}",
        code=comp.code,
        module_type=comp.module_type,
    )

    return {
        "component_id": new_comp.id,
        "cloned_from": component_id,
    }


@router.post("/components/{component_id}/run")
async def run_component(
    component_id: str,
    body: RunInputsRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    registry = _registry(request)

    # Ensure compiled
    if not registry.is_loaded(component_id):
        repo = Repository(db)
        comp_def = await repo.get_component(component_id)
        if not comp_def:
            raise HTTPException(status_code=404, detail="Component not found")
        try:
            registry.compile(comp_def)
        except ComponentCompileError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    module = registry.instantiate(component_id)
    if module is None:
        raise HTTPException(status_code=500, detail="Component could not be instantiated")

    loop = asyncio.get_running_loop()
    try:
        prediction = await loop.run_in_executor(
            None, functools.partial(module, **body.inputs)
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Component run failed: {exc}") from exc

    outputs: dict[str, Any] = {}
    if hasattr(prediction, "toDict"):
        outputs = prediction.toDict()
    elif hasattr(prediction, "__dict__"):
        outputs = {k: v for k, v in prediction.__dict__.items() if not k.startswith("_")}

    return {"component_id": component_id, "inputs": body.inputs, "outputs": outputs}


# ── Pipeline endpoints ────────────────────────────────────────────────────────


@router.get("/pipelines")
async def list_pipelines(
    db: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    repo = Repository(db)
    pipelines = await repo.list_pipelines()
    return [_pipeline_to_dict(p) for p in pipelines]


@router.post("/pipelines", status_code=201)
async def create_pipeline(
    body: PipelineCreateRequest,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    pipeline = PipelineDef(
        id=f"pipe_{uuid.uuid4().hex[:10]}",
        name=body.name,
        description=body.description,
        steps=body.steps,
    )
    repo = Repository(db)
    saved = await repo.save_pipeline(pipeline)
    return _pipeline_to_dict(saved)


@router.get("/pipelines/{pipeline_id}")
async def get_pipeline(
    pipeline_id: str,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    repo = Repository(db)
    pipeline = await repo.get_pipeline(pipeline_id)
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    return _pipeline_to_dict(pipeline)


@router.put("/pipelines/{pipeline_id}")
async def update_pipeline(
    pipeline_id: str,
    body: PipelineUpdateRequest,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    repo = Repository(db)
    pipeline = await repo.get_pipeline(pipeline_id)
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    if body.name is not None:
        pipeline.name = body.name
    if body.description is not None:
        pipeline.description = body.description
    if body.steps is not None:
        pipeline.steps = body.steps
    if body.is_active is not None:
        pipeline.is_active = body.is_active

    saved = await repo.save_pipeline(pipeline)
    return _pipeline_to_dict(saved)


@router.delete("/pipelines/{pipeline_id}", status_code=204)
async def delete_pipeline(
    pipeline_id: str,
    db: AsyncSession = Depends(get_session),
) -> None:
    repo = Repository(db)
    pipeline = await repo.get_pipeline(pipeline_id)
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    await repo.delete_pipeline(pipeline_id)


@router.post("/pipelines/{pipeline_id}/run")
async def run_pipeline(
    pipeline_id: str,
    body: RunInputsRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    repo = Repository(db)
    pipeline_def = await repo.get_pipeline(pipeline_id)
    if not pipeline_def:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    registry = _registry(request)
    # Ensure all components are loaded
    for step in pipeline_def.steps:
        cid = step.get("component_id")
        if cid and not registry.is_loaded(cid):
            comp_def = await repo.get_component(cid)
            if comp_def:
                try:
                    registry.compile(comp_def)
                except ComponentCompileError as exc:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Component {cid!r} failed to compile: {exc}",
                    ) from exc

    builder = _pipeline_builder(request)
    try:
        prediction = await builder.build_and_run(pipeline_def, body.inputs)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    outputs: dict[str, Any] = {}
    if hasattr(prediction, "toDict"):
        outputs = prediction.toDict()
    elif hasattr(prediction, "__dict__"):
        outputs = {k: v for k, v in prediction.__dict__.items() if not k.startswith("_")}

    return {"pipeline_id": pipeline_id, "inputs": body.inputs, "outputs": outputs}


# ── Serialisation helpers ─────────────────────────────────────────────────────


def _component_to_dict(c: DSPyComponentDef) -> dict[str, Any]:
    return {
        "id": c.id,
        "name": c.name,
        "description": c.description,
        "signature_fields": c.signature_fields,
        "code": c.code,
        "module_type": c.module_type,
        "is_active": c.is_active,
        "created_at": c.created_at.isoformat(),
        "updated_at": c.updated_at.isoformat(),
    }


def _pipeline_to_dict(p: PipelineDef) -> dict[str, Any]:
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "steps": p.steps,
        "is_active": p.is_active,
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat(),
    }
