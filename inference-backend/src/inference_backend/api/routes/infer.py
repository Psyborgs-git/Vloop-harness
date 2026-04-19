from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Any

router = APIRouter()


class InferRequest(BaseModel):
    module: str
    inputs: dict[str, Any]


@router.post("/infer")
async def infer(req: InferRequest, request: Request):
    registry = request.app.state.module_registry
    mod = registry.get(req.module)
    if mod is None:
        raise HTTPException(status_code=404, detail=f"Module '{req.module}' not found")
    if not hasattr(mod, "run"):
        raise HTTPException(status_code=400, detail=f"Module '{req.module}' has no run() function")
    result = mod.run(**req.inputs)
    return {"result": result}
