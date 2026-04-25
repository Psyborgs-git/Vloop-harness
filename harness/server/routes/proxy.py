"""UI mounting proxy routes.

Supports:
  - Root dashboard mount (`/ui/root`) via Vite dev server.
  - Stable generated-view mounts (`/ui/views/{view_ref}`).
  - Stable app-manifest mounts (`/ui/apps/{manifest_id}`).
  - Legacy component mounts (`/ui/{component_id}`).
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from harness.data.db import get_session
from harness.data.repository import Repository
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


def _render_shell_html(
    *,
    request: Request,
    component_id: str,
    module_src: str,
    css_hrefs: list[str] | None = None,
    initial_state: dict[str, object] | None = None,
    permissions: list[str] | None = None,
) -> HTMLResponse:
    settings = request.app.state.settings
    api_base = f"http://{settings.harness_host}:{settings.harness_port}"
    ws_base = f"ws://{settings.harness_host}:{settings.harness_port}"
    css_tags = "\n".join(f'<link rel="stylesheet" href="{href}" />' for href in (css_hrefs or []))
    shell = (
        "<!doctype html><html><head><meta charset=\"UTF-8\" />"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />"
        f"{css_tags}"
        "</head><body><div id=\"root\"></div>"
        f"<script type=\"module\" src=\"{module_src}\"></script>"
        "</body></html>"
    )
    html = inject_harness_vars(
        html=shell,
        component_id=component_id,
        api_base=api_base,
        ws_base=ws_base,
        initial_state=initial_state or {},
        permissions=permissions or [],
    )
    return HTMLResponse(content=html, status_code=200)


def _react_project_dir(request: Request) -> Path:
    storage = request.app.state.vloop_storage
    return storage.project_dir.parent / "react"


def _load_vite_manifest(react_dir: Path) -> dict[str, object]:
    manifest_path = react_dir / "dist" / ".vite" / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Built UI assets not found. Run frontend build to serve static manifests/views.",
        )
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Invalid Vite manifest.json") from exc


def _resolve_dist_entry(
    *,
    react_dir: Path,
    entry_key: str,
) -> tuple[str, list[str]]:
    manifest = _load_vite_manifest(react_dir)
    entry = manifest.get(entry_key)
    if not isinstance(entry, dict):
        raise HTTPException(
            status_code=404,
            detail=f"Built entry missing for {entry_key}. Rebuild the frontend.",
        )
    js_file = entry.get("file")
    if not isinstance(js_file, str):
        raise HTTPException(status_code=500, detail=f"Invalid built entry metadata for {entry_key}")
    css = entry.get("css")
    css_files = [f"/dist/{item}" for item in css] if isinstance(css, list) else []
    return f"/dist/{js_file}", css_files


async def _resolve_view_component_name(
    view_ref: str,
    db: AsyncSession,
) -> tuple[str, str]:
    repo = Repository(db)
    view = await repo.resolve_view_ref(view_ref)
    if view is None:
        raise HTTPException(status_code=404, detail="Generated view not found")
    return view.id, view.component_name


# ── Root dashboard (special-cased — not a legacy component) ──────────────────

@router.get("/ui/root")
@router.get("/ui/root/{path:path}")
async def serve_root_ui(request: Request, path: str = "") -> Response:
    """Serve the main VLoop Harness dashboard from react/index.html."""
    settings = request.app.state.settings
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


@router.get("/dist/{path:path}")
async def static_dist_assets(path: str, request: Request) -> Response:
    react_dir = _react_project_dir(request)
    asset_path = react_dir / "dist" / path
    if not asset_path.exists() or not asset_path.is_file():
        raise HTTPException(status_code=404, detail="Static asset not found")
    return FileResponse(asset_path)


# ── Stable generated UI mounts ──────────────────────────────────────────────

@router.get("/ui/views/{view_ref}")
@router.get("/ui/views/{view_ref}/{path:path}")
async def serve_view_ui(
    view_ref: str,
    request: Request,
    db: AsyncSession = Depends(get_session),
    path: str = "",
) -> Response:
    _ = path  # client-side routing only; shell mount is stable for all sub-paths
    view_id, component_name = await _resolve_view_component_name(view_ref, db)
    settings = request.app.state.settings

    entry_key = f"src/components/generated/{component_name}/main.tsx"
    if settings.harness_debug:
        return _render_shell_html(
            request=request,
            component_id=f"view:{view_id}",
            module_src=f"/{entry_key}",
        )

    js_src, css_hrefs = _resolve_dist_entry(react_dir=_react_project_dir(request), entry_key=entry_key)
    return _render_shell_html(
        request=request,
        component_id=f"view:{view_id}",
        module_src=js_src,
        css_hrefs=css_hrefs,
    )


@router.get("/ui/apps/{manifest_id}")
@router.get("/ui/apps/{manifest_id}/{path:path}")
async def serve_manifest_ui(
    manifest_id: str,
    request: Request,
    db: AsyncSession = Depends(get_session),
    path: str = "",
) -> Response:
    _ = path
    repo = Repository(db)
    manifest = await repo.get_app_manifest(manifest_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="App manifest not found")
    if not manifest.react_views:
        raise HTTPException(status_code=404, detail="App manifest has no linked React views")

    view = await repo.resolve_view_ref(manifest.react_views[0])
    if view is None:
        raise HTTPException(status_code=404, detail="Manifest linked view not found")

    entry_key = f"src/components/generated/{view.component_name}/main.tsx"
    settings = request.app.state.settings
    if settings.harness_debug:
        return _render_shell_html(
            request=request,
            component_id=f"app:{manifest.id}",
            module_src=f"/{entry_key}",
            permissions=manifest.permissions,
        )

    js_src, css_hrefs = _resolve_dist_entry(react_dir=_react_project_dir(request), entry_key=entry_key)
    return _render_shell_html(
        request=request,
        component_id=f"app:{manifest.id}",
        module_src=js_src,
        css_hrefs=css_hrefs,
        permissions=manifest.permissions,
    )


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
