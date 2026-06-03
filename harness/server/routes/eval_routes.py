"""REST routes for component versioning, rollback, eval datasets, and evaluation.

Endpoints
─────────
  GET    /api/dspy/components/{id}/versions               — list component versions
  POST   /api/dspy/components/{id}/snapshot               — snapshot current state as a new version
  POST   /api/dspy/components/{id}/rollback               — rollback to a previous version

  GET    /api/dspy/components/{id}/eval-datasets          — list eval datasets
  POST   /api/dspy/components/{id}/eval-datasets          — create an eval dataset
  PUT    /api/dspy/components/{id}/eval-datasets/{did}    — update an eval dataset
  DELETE /api/dspy/components/{id}/eval-datasets/{did}    — delete an eval dataset

  POST   /api/dspy/components/{id}/evaluate               — run evaluation using a stored dataset
"""

from __future__ import annotations

import asyncio
import functools
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from harness.data.db import get_session
from harness.data.repository import Repository

router = APIRouter(prefix="/api/dspy", tags=["eval"])


# ── Request / Response models ─────────────────────────────────────────────────


class SnapshotRequest(BaseModel):
    change_summary: str = ""


class RollbackRequest(BaseModel):
    version_id: str


class EvalDatasetCreateRequest(BaseModel):
    name: str
    description: str = ""
    examples: list[dict[str, Any]] = []


class EvalDatasetUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    examples: list[dict[str, Any]] | None = None


class EvaluateRequest(BaseModel):
    dataset_id: str | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────


def _version_to_dict(v: Any) -> dict[str, Any]:
    return {
        "id": v.id,
        "component_id": v.component_id,
        "version_number": v.version_number,
        "name": v.name,
        "description": v.description,
        "code": v.code,
        "module_type": v.module_type,
        "change_summary": v.change_summary,
        "created_at": v.created_at.isoformat(),
    }


def _dataset_to_dict(d: Any) -> dict[str, Any]:
    return {
        "id": d.id,
        "component_id": d.component_id,
        "name": d.name,
        "description": d.description,
        "examples": d.examples,
        "created_at": d.created_at.isoformat(),
        "updated_at": d.updated_at.isoformat(),
    }


def _registry(request: Request) -> Any:
    return request.app.state.component_registry


# ── Versioning endpoints ──────────────────────────────────────────────────────


@router.get("/components/{component_id}/versions")
async def list_versions(
    component_id: str,
    db: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    repo = Repository(db)
    comp = await repo.get_component(component_id)
    if not comp:
        raise HTTPException(status_code=404, detail="Component not found")
    versions = await repo.list_component_versions(component_id)
    return [_version_to_dict(v) for v in versions]


@router.post("/components/{component_id}/snapshot", status_code=201)
async def snapshot_component(
    component_id: str,
    body: SnapshotRequest,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Capture the current state of a component as a new immutable version."""
    repo = Repository(db)
    comp = await repo.get_component(component_id)
    if not comp:
        raise HTTPException(status_code=404, detail="Component not found")

    version = await repo.create_component_version(
        component_id=component_id,
        name=comp.name,
        code=comp.code,
        description=comp.description,
        module_type=comp.module_type,
        change_summary=body.change_summary,
    )
    return _version_to_dict(version)


@router.post("/components/{component_id}/rollback")
async def rollback_component(
    component_id: str,
    body: RollbackRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Rollback a component to a previous version.

    Before rolling back, a snapshot of the current state is created
    (change_summary="pre-rollback snapshot") so the rollback itself is
    reversible.
    """
    repo = Repository(db)
    comp = await repo.get_component(component_id)
    if not comp:
        raise HTTPException(status_code=404, detail="Component not found")

    target = await repo.get_component_version(body.version_id)
    if not target or target.component_id != component_id:
        raise HTTPException(status_code=404, detail="Version not found")

    # Snapshot current state before overwriting
    await repo.create_component_version(
        component_id=component_id,
        name=comp.name,
        code=comp.code,
        description=comp.description,
        module_type=comp.module_type,
        change_summary="pre-rollback snapshot",
    )

    # Apply the chosen version's fields back onto the live component
    comp.name = target.name
    comp.description = target.description
    comp.code = target.code
    comp.module_type = target.module_type

    # Re-extract signature fields and recompile
    from harness.engine.component_registry import ComponentCompileError, DSPyComponentRegistry

    comp.signature_fields = DSPyComponentRegistry.extract_signature_fields(comp.code)
    registry = _registry(request)
    try:
        registry.compile(comp)
    except ComponentCompileError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    saved = await repo.save_component(comp)
    return {
        "component_id": component_id,
        "rolled_back_to": body.version_id,
        "component": {
            "id": saved.id,
            "name": saved.name,
            "description": saved.description,
            "code": saved.code,
            "module_type": saved.module_type,
            "updated_at": saved.updated_at.isoformat(),
        },
    }


# ── Eval dataset endpoints ────────────────────────────────────────────────────


@router.get("/components/{component_id}/eval-datasets")
async def list_eval_datasets(
    component_id: str,
    db: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    repo = Repository(db)
    comp = await repo.get_component(component_id)
    if not comp:
        raise HTTPException(status_code=404, detail="Component not found")
    datasets = await repo.list_eval_datasets(component_id)
    return [_dataset_to_dict(d) for d in datasets]


@router.post("/components/{component_id}/eval-datasets", status_code=201)
async def create_eval_dataset(
    component_id: str,
    body: EvalDatasetCreateRequest,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    repo = Repository(db)
    comp = await repo.get_component(component_id)
    if not comp:
        raise HTTPException(status_code=404, detail="Component not found")
    dataset = await repo.create_eval_dataset(
        component_id=component_id,
        name=body.name,
        description=body.description,
        examples=body.examples,
    )
    return _dataset_to_dict(dataset)


@router.put("/components/{component_id}/eval-datasets/{dataset_id}")
async def update_eval_dataset(
    component_id: str,
    dataset_id: str,
    body: EvalDatasetUpdateRequest,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    repo = Repository(db)
    dataset = await repo.get_eval_dataset(dataset_id)
    if not dataset or dataset.component_id != component_id:
        raise HTTPException(status_code=404, detail="Eval dataset not found")

    updates: dict[str, Any] = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.description is not None:
        updates["description"] = body.description
    if body.examples is not None:
        updates["examples"] = body.examples

    if updates:
        await repo.update_eval_dataset(dataset_id, **updates)

    refreshed = await repo.get_eval_dataset(dataset_id)
    return _dataset_to_dict(refreshed)


@router.delete("/components/{component_id}/eval-datasets/{dataset_id}", status_code=204)
async def delete_eval_dataset(
    component_id: str,
    dataset_id: str,
    db: AsyncSession = Depends(get_session),
) -> None:
    repo = Repository(db)
    dataset = await repo.get_eval_dataset(dataset_id)
    if not dataset or dataset.component_id != component_id:
        raise HTTPException(status_code=404, detail="Eval dataset not found")
    await repo.delete_eval_dataset(dataset_id)


# ── Evaluate endpoint ─────────────────────────────────────────────────────────


@router.post("/components/{component_id}/evaluate")
async def evaluate_component(
    component_id: str,
    body: EvaluateRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Run a component against each example in a stored eval dataset.

    Compares output field values against expected_outputs using
    case-insensitive exact string match.  Returns per-example pass/fail
    and overall statistics.
    """
    repo = Repository(db)
    comp = await repo.get_component(component_id)
    if not comp:
        raise HTTPException(status_code=404, detail="Component not found")

    # Resolve dataset
    if body.dataset_id:
        dataset = await repo.get_eval_dataset(body.dataset_id)
        if not dataset or dataset.component_id != component_id:
            raise HTTPException(status_code=404, detail="Eval dataset not found")
    else:
        datasets = await repo.list_eval_datasets(component_id)
        if not datasets:
            raise HTTPException(status_code=404, detail="No eval datasets found for this component")
        dataset = datasets[0]  # use most-recent

    # Ensure component is compiled
    registry = _registry(request)
    from harness.engine.component_registry import ComponentCompileError

    if not registry.is_loaded(component_id):
        try:
            registry.compile(comp)
        except ComponentCompileError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    loop = asyncio.get_running_loop()
    results: list[dict[str, Any]] = []
    passed = 0
    failed = 0

    for idx, example in enumerate(dataset.examples):
        inputs: dict[str, Any] = example.get("inputs", {})
        expected: dict[str, Any] = example.get("expected_outputs", {})

        try:
            module = registry.instantiate(component_id)
            prediction = await loop.run_in_executor(
                None, functools.partial(module, **inputs)
            )
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Component %s failed on example %d: %s", component_id, idx, exc
            )
            results.append({
                "index": idx,
                "passed": False,
                "error": "Component execution failed",
                "inputs": inputs,
                "expected_outputs": expected,
                "actual_outputs": {},
            })
            failed += 1
            continue

        actual: dict[str, Any] = {}
        if hasattr(prediction, "toDict"):
            actual = prediction.toDict()
        elif hasattr(prediction, "__dict__"):
            actual = {k: v for k, v in prediction.__dict__.items() if not k.startswith("_")}

        # Compare each expected field (case-insensitive string match)
        field_results: dict[str, bool] = {}
        example_passed = True
        for field, exp_val in expected.items():
            act_val = actual.get(field)
            match = str(act_val).strip().lower() == str(exp_val).strip().lower()
            field_results[field] = match
            if not match:
                example_passed = False

        if example_passed:
            passed += 1
        else:
            failed += 1

        results.append({
            "index": idx,
            "passed": example_passed,
            "inputs": inputs,
            "expected_outputs": expected,
            "actual_outputs": actual,
            "field_results": field_results,
        })

    return {
        "component_id": component_id,
        "dataset_id": dataset.id,
        "total": len(dataset.examples),
        "passed": passed,
        "failed": failed,
        "results": results,
    }


# ── View versioning endpoints ──────────────────────────────────────────────────


class ViewSnapshotRequest(BaseModel):
    file_path: str
    source: str
    prompt: str | None = None
    agent_run_id: str | None = None
    change_summary: str = ""


@router.get("/views/{view_id}/versions")
async def list_view_versions(
    view_id: str,
    db: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """List all versions of a view."""
    repo = Repository(db)
    versions = await repo.list_view_versions(view_id)
    return [{
        "id": v.id,
        "view_id": v.view_id,
        "version_number": v.version_number,
        "file_path": v.file_path,
        "change_summary": v.change_summary,
        "created_at": v.created_at.isoformat(),
    } for v in versions]


@router.post("/views/{view_id}/snapshot")
async def snapshot_view(
    view_id: str,
    body: ViewSnapshotRequest,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Create a snapshot of a view as a new version."""
    repo = Repository(db)
    version = await repo.create_view_version(
        view_id=view_id,
        file_path=body.file_path,
        source=body.source,
        prompt=body.prompt,
        agent_run_id=body.agent_run_id,
        change_summary=body.change_summary,
    )
    return {
        "id": version.id,
        "view_id": version.view_id,
        "version_number": version.version_number,
        "file_path": version.file_path,
        "change_summary": version.change_summary,
        "created_at": version.created_at.isoformat(),
    }


@router.post("/views/{view_id}/rollback")
async def rollback_view(
    view_id: str,
    body: RollbackRequest,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Rollback a view to a previous version."""
    repo = Repository(db)
    version = await repo.get_view_version(body.version_id)
    if not version or version.view_id != view_id:
        raise HTTPException(status_code=404, detail="View version not found")

    # In a real implementation, this would write the source back to the file
    # For now, just return the version info
    return {
        "view_id": view_id,
        "rolled_back_to": version.version_number,
        "source": version.source,
        "file_path": version.file_path,
    }
