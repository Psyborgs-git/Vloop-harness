"""REST routes for the DAG-based pipeline framework.

Endpoints
─────────
  POST /api/pipelines/build       — build a pipeline from a template
  POST /api/pipelines/run          — execute a pipeline graph
  GET  /api/pipelines/templates    — list available pipeline templates
  POST /api/pipelines/validate     — validate a pipeline graph JSON
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from harness.engine.pipelines.base import NodeType, PipelineGraph
from harness.engine.pipelines.executor import ExecutionContext, PipelineExecutor
from harness.engine.pipelines.templates import (
    AgentLoopPipeline,
    MapReducePipeline,
    RAGPipeline,
    ReflectionPipeline,
    SequentialPipeline,
    run_pipeline,
)

router = APIRouter(prefix="/api/pipelines", tags=["pipelines"])


# ── Request / Response models ─────────────────────────────────────────────────


class SequentialPipelineRequest(BaseModel):
    name: str = "sequential"
    steps: list[dict[str, Any]] = []
    inputs: dict[str, Any] = {}


class RAGPipelineRequest(BaseModel):
    query: str
    retriever_component_id: str | None = None
    generator_component_id: str | None = None
    top_k: int = 5


class RunPipelineRequest(BaseModel):
    graph: dict[str, Any]
    inputs: dict[str, Any] = {}


class ValidatePipelineRequest(BaseModel):
    graph: dict[str, Any]


# ── Helpers ───────────────────────────────────────────────────────────────────


def _mp(request: Request):
    return request.app.state.main_process


def _registry(request: Request):
    return request.app.state.component_registry


def _execution_context_to_dict(ctx: ExecutionContext) -> dict[str, Any]:
    return {
        "inputs": ctx.inputs,
        "outputs": ctx.outputs,
        "step_results": [s.to_dict() for s in ctx.step_results],
    }


# ── Template endpoints ────────────────────────────────────────────────────────


@router.get("/templates")
async def list_templates() -> list[dict[str, str]]:
    """List built-in pipeline templates."""
    return [
        {"id": "sequential", "name": "Sequential", "description": "Linear step execution"},
        {"id": "rag", "name": "RAG", "description": "Retrieval-Augmented Generation"},
        {"id": "map_reduce", "name": "MapReduce", "description": "Parallel map with reduce"},
        {"id": "agent_loop", "name": "AgentLoop", "description": "Think-act-observe loop"},
        {"id": "reflection", "name": "Reflection", "description": "Generate-critique-revise"},
    ]


@router.post("/build/sequential")
async def build_sequential(body: SequentialPipelineRequest) -> dict[str, Any]:
    """Build a sequential pipeline."""
    pipeline = SequentialPipeline(name=body.name)
    for step in body.steps:
        pipeline.add_step(step.get("name", "step"), step.get("config", {}))
    graph = pipeline.build()
    return {"graph": graph.to_dict(), "validation_errors": graph.validate()}


@router.post("/run")
async def run_pipeline_endpoint(
    body: RunPipelineRequest,
    request: Request,
) -> dict[str, Any]:
    """Execute a pipeline graph with inputs."""
    graph = _deserialize_graph(body.graph)
    errors = graph.validate()
    if errors:
        raise HTTPException(status_code=422, detail=errors)

    mp = _mp(request)
    executor = PipelineExecutor(graph)
    ctx = await executor.run(body.inputs, tool_registry=mp.tools)
    return _execution_context_to_dict(ctx)


@router.post("/validate")
async def validate_pipeline(body: ValidatePipelineRequest) -> dict[str, Any]:
    """Validate a pipeline graph without executing."""
    try:
        graph = _deserialize_graph(body.graph)
        errors = graph.validate()
        return {"valid": len(errors) == 0, "errors": errors, "graph": graph.to_dict()}
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ── Deserialization helper ────────────────────────────────────────────────────


def _deserialize_graph(data: dict[str, Any]) -> PipelineGraph:
    """Rebuild a PipelineGraph from a JSON dict."""
    graph = PipelineGraph(name=data.get("name", "pipeline"))
    node_id_map: dict[str, str] = {}

    for n in data.get("nodes", []):
        nid = graph.add_node(
            node_type=NodeType(n["type"]),
            name=n.get("name", ""),
            node_id=n.get("id"),
            config=n.get("config", {}),
        )
        node_id_map[n.get("id", nid)] = nid

    for e in data.get("edges", []):
        src = node_id_map.get(e["source"], e["source"])
        tgt = node_id_map.get(e["target"], e["target"])
        graph.add_edge(
            source=src,
            target=tgt,
            label=e.get("label", ""),
            input_map=e.get("input_map", {}),
        )

    return graph
