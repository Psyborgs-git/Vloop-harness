"""Vite proxy — /ui/{component_id}/{*path} forwards to Vite dev server and injects env vars.

The special-cased ``/ui/root`` route serves the main dashboard (react/index.html) without
requiring a legacy component registration.  All Vite asset paths (``/src/…``, ``/@vite/…``,
``/@react-refresh``, ``/node_modules/…``) are also forwarded so the browser can load the
React app's JS/CSS from the FastAPI origin.
"""

from __future__ import annotations

from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from harness.server.injector import inject_harness_vars

router = APIRouter()


def _react_dist_dir(settings: object) -> Path:
    """Resolve the built React dist directory for static mode."""
    configured = getattr(settings, "react_dist_dir", "")
    if configured:
        return Path(str(configured)).expanduser().resolve()
    return (Path(__file__).resolve().parents[3] / "react" / "dist").resolve()


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


# ── Root dashboard (special-cased — not a legacy component) ──────────────────

@router.get("/ui/root")
@router.get("/ui/root/{path:path}")
async def serve_root_ui(request: Request, path: str = "") -> Response:
    """Serve the main VLoop Harness dashboard from react/index.html."""
    settings = request.app.state.settings
    vite_url = f"http://{settings.vite_host}:{settings.vite_port}"
    debug_mode = bool(getattr(settings, "harness_debug", True))

    if not debug_mode:
        dist_dir = _react_dist_dir(settings)
        if not dist_dir.exists():
            raise HTTPException(status_code=503, detail=f"React dist directory not found: {dist_dir}")

        rel = path or "index.html"
        candidate = (dist_dir / rel).resolve()
        try:
            candidate.relative_to(dist_dir)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Asset not found") from exc
        if not candidate.exists() or not candidate.is_file():
            raise HTTPException(status_code=404, detail="Asset not found")
        content = candidate.read_text(encoding="utf-8") if candidate.suffix == ".html" else candidate.read_bytes()
        if candidate.suffix != ".html":
            return Response(content=content)

        api_base = f"http://{settings.harness_host}:{settings.harness_port}"
        ws_base = f"ws://{settings.harness_host}:{settings.harness_port}"
        html = inject_harness_vars(
            html=str(content),
            component_id="root",
            api_base=api_base,
            ws_base=ws_base,
            initial_state={},
            permissions=[],
        )
        return HTMLResponse(content=html)

    # Non-HTML sub-paths (e.g. HMR WebSocket upgrade requests) go straight to Vite.
    if path:
        return await _proxy_to_vite(path, vite_url)

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{vite_url}/", follow_redirects=True, timeout=10)
        except httpx.ConnectError as exc:
            raise HTTPException(status_code=503, detail="Vite dev server unreachable") from exc

    api_base = f"http://{settings.harness_host}:{settings.harness_port}"
    ws_base = f"ws://{settings.harness_host}:{settings.harness_port}"

    html = inject_harness_vars(
        html=resp.text,
        component_id="root",
        api_base=api_base,
        ws_base=ws_base,
        initial_state={},
        permissions=[],
    )
    return HTMLResponse(content=html, status_code=resp.status_code)


# ── Vite asset pass-through ───────────────────────────────────────────────────
# The injected HTML has module scripts with src="/src/…" and Vite-internal
# paths like "/@vite/client" and "/@react-refresh".  The browser resolves
# these against the FastAPI origin, so we must forward them to Vite.

@router.get("/src/{path:path}")
async def vite_src(path: str, request: Request) -> Response:
    settings = request.app.state.settings
    vite_url = f"http://{settings.vite_host}:{settings.vite_port}"
    return await _proxy_to_vite(f"src/{path}", vite_url)


@router.get("/@{path:path}")
async def vite_internal(path: str, request: Request) -> Response:
    settings = request.app.state.settings
    vite_url = f"http://{settings.vite_host}:{settings.vite_port}"
    return await _proxy_to_vite(f"@{path}", vite_url)


@router.get("/node_modules/{path:path}")
async def vite_node_modules(path: str, request: Request) -> Response:
    settings = request.app.state.settings
    vite_url = f"http://{settings.vite_host}:{settings.vite_port}"
    return await _proxy_to_vite(f"node_modules/{path}", vite_url)


# ── Legacy component UI ───────────────────────────────────────────────────────

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
