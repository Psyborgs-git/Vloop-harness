"""REST endpoints for component CRUD and state management."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()


class ComponentCreateRequest(BaseModel):
    class_path: str
    props: dict[str, Any] = {}
    permissions: list[str] = []


class EventRequest(BaseModel):
    name: str
    payload: Any = None


class PropsUpdateRequest(BaseModel):
    props: dict[str, Any]


# ── Static routes ─────────────────────────────────────────────────────────────


@router.get("/api/components")
async def list_components(request: Request) -> list[dict[str, Any]]:
    mp = request.app.state.main_process
    return [c.get_snapshot() for c in mp.component_tree.list_all()]


@router.post("/api/components", status_code=201)
async def create_component(body: ComponentCreateRequest, request: Request) -> dict[str, Any]:
    import importlib

    mp = request.app.state.main_process
    module_path, class_name = body.class_path.rsplit(".", 1)
    try:
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
    except (ImportError, AttributeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    from harness.core.permissions import Permission

    perms: set[Permission] = set()
    for p in body.permissions:
        try:
            perms.add(Permission(p))
        except ValueError:
            pass

    comp = cls(props=body.props)
    await mp.register(comp, permissions=perms)
    return comp.get_snapshot()


@router.delete("/api/components/{component_id}", status_code=204)
async def destroy_component(component_id: str, request: Request) -> None:
    mp = request.app.state.main_process
    if component_id not in mp.component_tree:
        raise HTTPException(status_code=404, detail="Component not found")
    await mp.unregister(component_id)


# ── Dynamic routes (registered at component mount time) ───────────────────────


@router.get("/api/{component_id}/state")
async def get_state(component_id: str, request: Request) -> dict[str, Any]:
    mp = request.app.state.main_process
    comp = mp.get_component(component_id)
    if comp is None:
        raise HTTPException(status_code=404, detail="Component not found")
    return comp.get_snapshot()


@router.post("/api/{component_id}/event")
async def post_event(component_id: str, body: EventRequest, request: Request) -> dict[str, str]:
    mp = request.app.state.main_process
    comp = mp.get_component(component_id)
    if comp is None:
        raise HTTPException(status_code=404, detail="Component not found")
    await comp.on_event(body.name, body.payload)
    return {"status": "ok"}


@router.post("/api/{component_id}/props")
async def update_props(component_id: str, body: PropsUpdateRequest, request: Request) -> dict[str, str]:
    mp = request.app.state.main_process
    comp = mp.get_component(component_id)
    if comp is None:
        raise HTTPException(status_code=404, detail="Component not found")
    await comp.on_update(body.props)
    return {"status": "ok"}


@router.get("/api/{component_id}/logs")
async def get_logs(component_id: str, request: Request, n: int = 100) -> list[dict[str, Any]]:
    mp = request.app.state.main_process
    return mp.logger.tail(component_id, n=n)
