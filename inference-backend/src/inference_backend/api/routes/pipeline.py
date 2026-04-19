from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Any

from ...self_modify.writer import write_pipeline
from ...self_modify.validator import validate
from ...self_modify.rollback import commit_module, rollback_module, list_versions

router = APIRouter()


class PipelineCreateRequest(BaseModel):
    name: str
    definition: dict[str, Any]


class PipelineRunRequest(BaseModel):
    name: str
    inputs: dict[str, Any]


class PipelineRollbackRequest(BaseModel):
    name: str
    version: str


@router.post("/pipeline/create")
async def pipeline_create(req: PipelineCreateRequest, request: Request):
    import json
    code = f'PIPELINE = {json.dumps(req.definition, indent=2)}\n\ndef run(inputs):\n    return PIPELINE\n'
    ok, msg = validate(code)
    if not ok:
        raise HTTPException(status_code=400, detail=f"Validation failed: {msg}")
    write_pipeline(req.name, code)
    sha = commit_module(req.name, f"[agent] create pipeline {req.name}")
    request.app.state.pipeline_registry.reload(req.name)
    return {"status": "ok", "sha": sha}


@router.post("/pipeline/run")
async def pipeline_run(req: PipelineRunRequest, request: Request):
    registry = request.app.state.pipeline_registry
    mod = registry.get(req.name)
    if mod is None:
        raise HTTPException(status_code=404, detail=f"Pipeline '{req.name}' not found")
    if not hasattr(mod, "run"):
        raise HTTPException(status_code=400, detail=f"Pipeline '{req.name}' has no run() function")
    result = mod.run(req.inputs)
    return {"result": result}


@router.get("/pipeline/list")
async def pipeline_list(request: Request):
    return {"pipelines": request.app.state.pipeline_registry.list()}


@router.post("/pipeline/rollback")
async def pipeline_rollback(req: PipelineRollbackRequest, request: Request):
    rollback_module(req.name, req.version)
    request.app.state.pipeline_registry.reload(req.name)
    return {"status": "ok"}
