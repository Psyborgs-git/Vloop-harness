"""REST routes for harness service management.

Endpoints
─────────
  GET  /api/services              — list all registered services and their status
  GET  /api/services/{name}       — get a single service's status/info
  POST /api/services/{name}/start   — start a service
  POST /api/services/{name}/stop    — stop a service
  POST /api/services/{name}/restart — restart a service
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/services", tags=["services"])


def _get_manager(request: Request):
    mp = request.app.state.main_process
    sm = getattr(mp, "_service_manager", None)
    if sm is None:
        raise HTTPException(status_code=503, detail="ServiceManager not initialised")
    return sm


@router.get("")
async def list_services(request: Request) -> list[dict[str, Any]]:
    """Return status info for all registered services."""
    sm = _get_manager(request)
    return [s.info() for s in sm.list_all()]


@router.get("/{name}")
async def get_service(name: str, request: Request) -> dict[str, Any]:
    """Return status info for a single service."""
    sm = _get_manager(request)
    service = sm.get(name)
    if service is None:
        raise HTTPException(status_code=404, detail=f"Service '{name}' not found")
    return service.info()


@router.post("/{name}/start", status_code=200)
async def start_service(name: str, request: Request) -> dict[str, Any]:
    """Start the named service (no-op if already running)."""
    sm = _get_manager(request)
    service = sm.get(name)
    if service is None:
        raise HTTPException(status_code=404, detail=f"Service '{name}' not found")
    try:
        await service.start()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return service.info()


@router.post("/{name}/stop", status_code=200)
async def stop_service(name: str, request: Request) -> dict[str, Any]:
    """Stop the named service (no-op if already stopped)."""
    sm = _get_manager(request)
    service = sm.get(name)
    if service is None:
        raise HTTPException(status_code=404, detail=f"Service '{name}' not found")
    try:
        await service.stop()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return service.info()


@router.post("/{name}/restart", status_code=200)
async def restart_service(name: str, request: Request) -> dict[str, Any]:
    """Restart the named service (stop then start)."""
    sm = _get_manager(request)
    service = sm.get(name)
    if service is None:
        raise HTTPException(status_code=404, detail=f"Service '{name}' not found")
    try:
        await service.restart()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return service.info()
