"""UI serving routes for debug (Vite proxy) and static (react/dist) modes.

`HARNESS_DEBUG=true`:
    /ui/* is proxied to Vite and HTML is injected with harness vars.
`HARNESS_DEBUG=false`:
    /ui/* is resolved from react/dist (entry HTML + static assets), with the same
    harness var injection on HTML responses.
"""

from __future__ import annotations

from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response

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


def _dist_root(request: Request) -> Path:
    return request.app.state.react_dist_dir


def _ensure_dist_available(dist_dir: Path) -> None:
    if not dist_dir.exists() or not dist_dir.is_dir():
        raise HTTPException(
            status_code=503,
            detail=(
                "Static UI build is unavailable: missing react/dist. "
                "Run `cd react && npm run build` or set HARNESS_DEBUG=true."
            ),
        )


def _safe_dist_file(dist_dir: Path, relative_path: str) -> Path | None:
    candidate = (dist_dir / relative_path).resolve()
    try:
        candidate.relative_to(dist_dir.resolve())
    except ValueError:
        return None
    if not candidate.is_file():
        return None
    return candidate


def _inject_html_from_dist(
    *,
    request: Request,
    entry_file: str,
    component_id: str,
    initial_state: dict,
    permissions: list[str],
) -> HTMLResponse:
    settings = request.app.state.settings
    dist_dir = _dist_root(request)
    _ensure_dist_available(dist_dir)
    html_file = dist_dir / entry_file

    if not html_file.exists():
        raise HTTPException(
            status_code=503,
            detail=(
                f"Static UI entry is unavailable: missing {entry_file} in react/dist. "
                "Rebuild frontend (`cd react && npm run build`) or set HARNESS_DEBUG=true."
            ),
        )

    try:
        raw_html = html_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read static UI entry {entry_file}: {exc}",
        ) from exc

    api_base = f"http://{settings.harness_host}:{settings.harness_port}"
    ws_base = f"ws://{settings.harness_host}:{settings.harness_port}"
    html = inject_harness_vars(
        html=raw_html,
        component_id=component_id,
        api_base=api_base,
        ws_base=ws_base,
        initial_state=initial_state,
        permissions=permissions,
    )
    return HTMLResponse(content=html, status_code=200)


# ── Root dashboard (special-cased — not a legacy component) ──────────────────

@router.get("/ui/root")
@router.get("/ui/root/{path:path}")
async def serve_root_ui(request: Request, path: str = "") -> Response:
    """Serve the main VLoop Harness dashboard from react/index.html."""
    settings = request.app.state.settings
    if not settings.harness_debug:
        dist_dir = _dist_root(request)
        _ensure_dist_available(dist_dir)

        if path:
            static_file = _safe_dist_file(dist_dir, path)
            if static_file is not None:
                return FileResponse(static_file)

        return _inject_html_from_dist(
            request=request,
            entry_file="root.html",
            component_id="root",
            initial_state={},
            permissions=[],
        )

    vite_url = f"http://{settings.vite_host}:{settings.vite_port}"

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
    if not settings.harness_debug:
        raise HTTPException(status_code=404, detail="Route unavailable outside debug mode")
    vite_url = f"http://{settings.vite_host}:{settings.vite_port}"
    return await _proxy_to_vite(f"src/{path}", vite_url)


@router.get("/@{path:path}")
async def vite_internal(path: str, request: Request) -> Response:
    settings = request.app.state.settings
    if not settings.harness_debug:
        raise HTTPException(status_code=404, detail="Route unavailable outside debug mode")
    vite_url = f"http://{settings.vite_host}:{settings.vite_port}"
    return await _proxy_to_vite(f"@{path}", vite_url)


@router.get("/node_modules/{path:path}")
async def vite_node_modules(path: str, request: Request) -> Response:
    settings = request.app.state.settings
    if not settings.harness_debug:
        raise HTTPException(status_code=404, detail="Route unavailable outside debug mode")
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

    if not settings.harness_debug:
        dist_dir = _dist_root(request)
        _ensure_dist_available(dist_dir)

        if path:
            static_file = _safe_dist_file(dist_dir, path)
            if static_file is not None:
                return FileResponse(static_file)

        perms = [p.value for p in comp.permissions.all_granted()]
        return _inject_html_from_dist(
            request=request,
            entry_file=f"{component_id}.html",
            component_id=component_id,
            initial_state=comp.state,
            permissions=perms,
        )

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
