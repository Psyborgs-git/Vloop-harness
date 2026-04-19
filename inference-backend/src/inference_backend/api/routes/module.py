from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ...self_modify.writer import write_module
from ...self_modify.validator import validate
from ...self_modify.rollback import commit_module, rollback_module, list_versions

router = APIRouter()


class ModuleCreateRequest(BaseModel):
    name: str
    code: str


class ModuleRollbackRequest(BaseModel):
    name: str
    version: str


@router.post("/module/create")
async def module_create(req: ModuleCreateRequest, request: Request):
    ok, msg = validate(req.code)
    if not ok:
        raise HTTPException(status_code=400, detail=f"Validation failed: {msg}")
    write_module(req.name, req.code)
    sha = commit_module(req.name)
    request.app.state.module_registry.reload(req.name)
    return {"status": "ok", "sha": sha}


@router.get("/module/list")
async def module_list(request: Request):
    return {"modules": request.app.state.module_registry.list()}


@router.post("/module/rollback")
async def module_rollback(req: ModuleRollbackRequest, request: Request):
    rollback_module(req.name, req.version)
    request.app.state.module_registry.reload(req.name)
    return {"status": "ok"}


@router.get("/module/{name}/versions")
async def module_versions(name: str):
    return {"versions": list_versions(name)}
