"""Vite proxy — /ui/{component_id}/{*path} forwards to Vite dev server and injects env vars."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from harness.server.injector import inject_harness_vars

router = APIRouter()


async def _proxy_to_vite(path: str, vite_url: str) -> Response:
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{vite_url}/{path}", follow_redirects=True, timeout=10)
        except httpx.ConnectError as exc:
            raise HTTPException(status_code=503, detail="Vite dev server unreachable") from exc

    headers = {
        k: v
        for k, v in resp.headers.items()
        if k.lower() not in ("content-encoding", "transfer-encoding", "content-length")
    }
    return Response(content=resp.content, status_code=resp.status_code, headers=headers)


@router.get("/ui/{component_id}")
@router.get("/ui/{component_id}/{path:path}")
async def serve_component_ui(
    component_id: str,
    request: Request,
    path: str = "",
) -> Response:
    mp = request.app.state.main_process
    settings = request.app.state.settings
    comp = mp.get_component(component_id)

    if comp is None:
        raise HTTPException(status_code=404, detail="Component not found")

    vite_url = f"http://{settings.vite_host}:{settings.vite_port}"
    vite_path = f"src/components/{component_id}/index.html" if not path else path

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"{vite_url}/{vite_path}",
                follow_redirects=True,
                timeout=10,
            )
        except httpx.ConnectError as exc:
            raise HTTPException(status_code=503, detail="Vite dev server unreachable") from exc

    content_type = resp.headers.get("content-type", "")
    if "text/html" not in content_type:
        headers = {
            k: v
            for k, v in resp.headers.items()
            if k.lower() not in ("content-encoding", "transfer-encoding", "content-length")
        }
        return Response(content=resp.content, status_code=resp.status_code, headers=headers)

    api_base = f"http://{settings.harness_host}:{settings.harness_port}"
    ws_base = f"ws://{settings.harness_host}:{settings.harness_port}"
    perms = [p.value for p in comp.permissions.all_granted()]

    html = inject_harness_vars(
        html=resp.text,
        component_id=component_id,
        api_base=api_base,
        ws_base=ws_base,
        initial_state=comp.state,
        permissions=perms,
    )
    return HTMLResponse(content=html, status_code=resp.status_code)
