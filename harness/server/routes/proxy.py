"""Vite proxy — /ui/{component_id}/{*path} forwards to Vite dev server and injects env vars.

The special-cased ``/ui/root`` route serves the main dashboard (react/index.html) without
requiring a legacy component registration.  All Vite asset paths (``/src/…``, ``/@vite/…``,
``/@react-refresh``, ``/node_modules/…``) are also forwarded so the browser can load the
React app's JS/CSS from the FastAPI origin.

Static fallback
───────────────
When the Vite dev server is not running, all UI routes fall back to the built
static files in ``react/dist/``.  Run ``npm run build`` inside the ``react/``
directory to produce these files.  The ``/assets/…`` paths in the built
``index.html`` are served by the ``StaticFiles`` mount registered in
``harness/server/app.py``.
"""

from __future__ import annotations

from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response

from harness.server.injector import inject_harness_vars

router = APIRouter()

# Absolute path to the pre-built React dist directory.
_REACT_DIST: Path = Path(__file__).parent.parent.parent.parent / "react" / "dist"


# ── Internal helpers ──────────────────────────────────────────────────────────


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


def _inject_and_return(html: str, settings: object) -> HTMLResponse:
    """Inject harness environment variables and return an HTMLResponse."""
    api_base = f"http://{settings.harness_host}:{settings.harness_port}"  # type: ignore[attr-defined]
    ws_base = f"ws://{settings.harness_host}:{settings.harness_port}"  # type: ignore[attr-defined]
    injected = inject_harness_vars(
        html=html,
        component_id="root",
        api_base=api_base,
        ws_base=ws_base,
        initial_state={},
        permissions=[],
    )
    return HTMLResponse(content=injected)


async def _serve_static_root(settings: object) -> HTMLResponse:
    """Serve the built ``react/dist/index.html`` with injected harness vars."""
    index = _REACT_DIST / "index.html"
    if not index.exists():
        raise HTTPException(
            status_code=503,
            detail=(
                "UI unavailable: Vite dev server is unreachable and no built static "
                "files were found. Run `npm run build` inside the `react/` directory."
            ),
        )
    return _inject_and_return(index.read_text(), settings)


async def _serve_static_asset(rel_path: str) -> Response:
    """Serve a static file from the built ``react/dist/`` tree."""
    target = (_REACT_DIST / rel_path).resolve()
    # Guard against path-traversal outside dist
    try:
        target.relative_to(_REACT_DIST.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid asset path")
    if target.is_file():
        return FileResponse(str(target))
    raise HTTPException(status_code=404, detail=f"Static asset not found: {rel_path}")


# ── Root dashboard (special-cased — not a legacy component) ──────────────────


@router.get("/ui/root")
@router.get("/ui/root/{path:path}")
async def serve_root_ui(request: Request, path: str = "") -> Response:
    """Serve the main VLoop Harness dashboard.

    Tries the Vite dev server first; falls back to the pre-built ``react/dist/``
    files when Vite is unreachable.
    """
    settings = request.app.state.settings
    vite_url = f"http://{settings.vite_host}:{settings.vite_port}"

    # Non-HTML sub-paths (e.g. HMR WebSocket upgrade requests) — try Vite then static.
    if path:
        try:
            return await _proxy_to_vite(path, vite_url)
        except HTTPException:
            return await _serve_static_asset(path)

    # Root index.html — try Vite then static dist.
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{vite_url}/", follow_redirects=True, timeout=10)
        return _inject_and_return(resp.text, settings)
    except (httpx.ConnectError, httpx.TimeoutException):
        return await _serve_static_root(settings)


# ── Vite asset pass-through ───────────────────────────────────────────────────
# The injected HTML has module scripts with src="/src/…" and Vite-internal
# paths like "/@vite/client" and "/@react-refresh".  The browser resolves
# these against the FastAPI origin, so we must forward them to Vite.
# (These paths are only present in development mode — production builds use
# /assets/… which is handled by the StaticFiles mount in app.py.)


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

