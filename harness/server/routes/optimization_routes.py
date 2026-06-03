"""REST routes for self-improvement, optimization, and evaluation.

Endpoints
─────────
  POST /api/optimization/improve          — run self-improvement on a component
  POST /api/optimization/evaluate           — evaluate a component
  POST /api/optimization/feedback          — submit user feedback
  GET  /api/optimization/feedback/{cid}   — get feedback summary for component
  POST /api/optimization/compare           — compare baseline vs optimized
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/optimization", tags=["optimization"])


# ── Request models ────────────────────────────────────────────────────────────


class ImproveRequest(BaseModel):
    component_id: str
    module_name: str = ""
    target_score: float = 0.85
    max_iterations: int = 3


class EvaluateRequest(BaseModel):
    component_id: str
    dataset_id: str | None = None
    metric_name: str = "contains"


class FeedbackRequest(BaseModel):
    component_id: str
    component_name: str = ""
    input_data: dict[str, Any] = {}
    output_data: dict[str, Any] = {}
    rating: int = 0
    comment: str = ""
    tags: list[str] = []


class CompareRequest(BaseModel):
    baseline_component_id: str
    optimized_component_id: str
    dataset_id: str | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────


def _ai(request: Request):
    return request.app.state.main_process.ai


def _registry(request: Request):
    return request.app.state.component_registry


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post("/improve")
async def improve_component(
    body: ImproveRequest,
    request: Request,
) -> dict[str, Any]:
    """Run the self-improvement loop on a compiled component."""
    ai = _ai(request)
    registry = _registry(request)

    module = registry.instantiate(body.component_id)
    if module is None:
        raise HTTPException(status_code=404, detail="Component not found or not compiled")

    name = body.module_name or body.component_id
    ai.self_improvement.config.target_score = body.target_score
    ai.self_improvement.config.max_iterations = body.max_iterations

    result = await ai.improve_component(module, name)
    return result.to_dict()


@router.post("/evaluate")
async def evaluate_component(
    body: EvaluateRequest,
    request: Request,
) -> dict[str, Any]:
    """Evaluate a compiled component against a dataset."""
    from harness.data.db import get_session
    from harness.data.repository import Repository
    from harness.engine.optimization.evaluator import Evaluator
    from sqlalchemy.ext.asyncio import AsyncSession

    ai = _ai(request)
    registry = _registry(request)
    module = registry.instantiate(body.component_id)
    if module is None:
        raise HTTPException(status_code=404, detail="Component not found or not compiled")

    # Load dataset if provided
    dataset: list[Any] = []
    if body.dataset_id:
        db: AsyncSession = await get_session().__anext__()  # type: ignore[attr-defined]
        repo = Repository(db)
        ds = await repo.get_eval_dataset(body.dataset_id)
        if ds:
            dataset = ds.examples

    evaluator = Evaluator()
    result = await evaluator.evaluate(module, dataset, metric_name=body.metric_name)
    return result.to_dict()


@router.post("/feedback")
async def submit_feedback(
    body: FeedbackRequest,
    request: Request,
) -> dict[str, Any]:
    """Record user feedback on a component output."""
    ai = _ai(request)
    entry = ai.self_improvement.feedback.record(
        component_id=body.component_id,
        component_name=body.component_name,
        input_data=body.input_data,
        output_data=body.output_data,
        rating=body.rating,
        comment=body.comment,
        tags=body.tags,
    )
    return entry.to_dict()


@router.get("/feedback/{component_id}")
async def get_feedback_summary(
    component_id: str,
    request: Request,
) -> dict[str, Any]:
    """Get feedback summary for a component."""
    ai = _ai(request)
    return ai.self_improvement.feedback.summary_for_component(component_id)


@router.post("/compare")
async def compare_versions(
    body: CompareRequest,
    request: Request,
) -> dict[str, Any]:
    """Compare baseline vs optimized component scores."""
    ai = _ai(request)
    registry = _registry(request)

    baseline = registry.instantiate(body.baseline_component_id)
    optimized = registry.instantiate(body.optimized_component_id)
    if baseline is None or optimized is None:
        raise HTTPException(status_code=404, detail="One or both components not found")

    from harness.engine.optimization.evaluator import Evaluator

    evaluator = Evaluator()
    # Use a minimal testset for comparison
    testset: list[Any] = []
    if body.dataset_id:
        from harness.data.db import get_session
        from harness.data.repository import Repository
        from sqlalchemy.ext.asyncio import AsyncSession

        db: AsyncSession = await get_session().__anext__()  # type: ignore[attr-defined]
        repo = Repository(db)
        ds = await repo.get_eval_dataset(body.dataset_id)
        if ds:
            testset = ds.examples

    metric = evaluator.get_metric("contains")
    return ai.self_improvement.optimizer.compare_versions(
        baseline, optimized, testset, metric
    )
