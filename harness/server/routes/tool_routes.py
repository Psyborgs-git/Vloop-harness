"""FastAPI routes for the tool runtime layer.

Endpoints
─────────
  GET    /api/tools                        — catalog of registered tools
  GET    /api/tools/policy                 — read effective policy
  PUT    /api/tools/policy                 — update project-local policy
  GET    /api/tools/workspace              — workspace root path

  POST   /api/tools/terminal               — execute a command
  POST   /api/tools/filesystem/list        — list directory
  POST   /api/tools/filesystem/read        — read file
  POST   /api/tools/filesystem/stat        — stat path
  POST   /api/tools/filesystem/write       — write file (202 if confirmation needed)
  POST   /api/tools/filesystem/create      — create file or directory
  POST   /api/tools/filesystem/delete      — delete (202 if confirmation needed)
  POST   /api/tools/filesystem/move        — move / rename (202 if confirmation needed)

  POST   /api/tools/browser                — browser automation (navigate, screenshot, …)
  POST   /api/tools/database               — database inspect / query

  POST   /api/tools/confirm/{token}        — confirm a pending destructive action
  DELETE /api/tools/confirm/{token}        — cancel a pending confirmation
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/tools", tags=["tools"])


# ── Request models ────────────────────────────────────────────────────────────


class ToolContext(BaseModel):
    component_id: str | None = None
    session_id: str | None = None


class TerminalRequest(ToolContext):
    command: str
    cwd_relative: str = "."
    timeout: int | None = None


class FilesystemRequest(ToolContext):
    path: str = "."
    content: str = ""
    create_parents: bool = False
    is_dir: bool = False
    recursive: bool = False
    src: str = ""
    dest: str = ""
    _confirmation_token: str | None = None


class PolicyUpdateRequest(BaseModel):
    permanent_blocklist: list[str] = []
    denylist: list[str] = []
    directories: list[dict[str, Any]] = []


class BrowserRequest(ToolContext):
    operation: str
    url: str = ""
    selector: str = ""
    value: str = ""
    expression: str = ""
    full_page: bool = False


class DatabaseRequest(ToolContext):
    operation: str
    sql: str = ""
    params: dict[str, Any] = {}


class RollbackRequest(BaseModel):
    path: str
    backup_index: int = -1


# ── Helper ────────────────────────────────────────────────────────────────────


def _mp(request: Request) -> Any:
    return request.app.state.main_process


def _confirmation_response(exc: Any) -> JSONResponse:
    """Translate a ConfirmationRequired exception into an HTTP 202."""
    content = {
        "requires_confirmation": True,
        "token": exc.token,
        "description": exc.description,
        "risk_level": exc.risk_level,
        "expires_in_seconds": 60,
    }

    # Include diff preview if available in the exception
    if hasattr(exc, 'action_params') and exc.action_params:
        diff_preview = exc.action_params.get("_diff_preview")
        diff_summary = exc.action_params.get("_diff_summary")
        if diff_preview:
            content["diff_preview"] = diff_preview
        if diff_summary:
            content["diff_summary"] = diff_summary

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=content,
    )


# ── Catalog + policy + workspace ──────────────────────────────────────────────


@router.get("")
async def list_tools(request: Request) -> list[dict[str, Any]]:
    """Return a catalog of all registered tools."""
    return _mp(request).tools.catalog()


@router.get("/policy")
async def get_policy(request: Request) -> dict[str, Any]:
    """Return the effective merged policy (global + project)."""
    import os

    import httpx
    ai_url = os.environ.get("RUST_BASE_AI_URL", "")
    if ai_url:
        rust_url = ai_url.rsplit("/v1", 1)[0]
        async with httpx.AsyncClient() as client:
            res = await client.get(f"{rust_url}/harness/tools/policy")
            return res.json()
    return _mp(request).tools.policy.effective.to_dict()


@router.put("/policy")
async def update_policy(body: PolicyUpdateRequest, request: Request) -> dict[str, Any]:
    """Persist an updated project-local policy and reload the engine."""
    import os

    import httpx
    ai_url = os.environ.get("RUST_BASE_AI_URL", "")
    if ai_url:
        rust_url = ai_url.rsplit("/v1", 1)[0]
        async with httpx.AsyncClient() as client:
            res = await client.put(f"{rust_url}/harness/tools/policy", json=body.model_dump())
            return res.json()

    from harness.tools.policy import DirectoryPolicy, PolicyConfig

    new_cfg = PolicyConfig(
        permanent_blocklist=body.permanent_blocklist,
        denylist=body.denylist,
        directories=[DirectoryPolicy.from_dict(d) for d in body.directories],
    )
    _mp(request).tools.policy.save_project_policy(new_cfg)
    return _mp(request).tools.policy.effective.to_dict()


@router.get("/workspace")
async def get_workspace(request: Request) -> dict[str, str]:
    """Return the workspace root path."""
    return {"workspace_root": str(_mp(request).workspace_root)}


# ── Terminal ──────────────────────────────────────────────────────────────────


@router.post("/terminal")
async def execute_terminal(body: TerminalRequest, request: Request) -> dict[str, Any]:
    """Execute a command within the workspace."""
    from harness.tools.exceptions import ConfirmationRequired

    params = {
        "command": body.command,
        "cwd_relative": body.cwd_relative,
    }
    if body.timeout is not None:
        params["timeout"] = body.timeout

    try:
        result = await _mp(request).tools.execute(
            tool_name="terminal",
            component_id=body.component_id,
            session_id=body.session_id,
            params=params,
        )
        return result.to_dict(redact_secrets=True)
    except ConfirmationRequired as exc:
        return _confirmation_response(exc)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── Filesystem ────────────────────────────────────────────────────────────────


async def _fs_call(
    request: Request,
    operation: str,
    params: dict[str, Any],
) -> JSONResponse | dict[str, Any]:
    from harness.tools.exceptions import ConfirmationRequired

    try:
        result = await _mp(request).tools.execute(
            tool_name="filesystem",
            component_id=params.pop("component_id", None),
            session_id=params.pop("session_id", None),
            params={"operation": operation, **params},
        )
        return result.to_dict(redact_secrets=True)
    except ConfirmationRequired as exc:
        return _confirmation_response(exc)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/filesystem/list")
async def fs_list(body: FilesystemRequest, request: Request) -> Any:
    return await _fs_call(
        request, "list",
        {"path": body.path, "component_id": body.component_id, "session_id": body.session_id},
    )


@router.post("/filesystem/read")
async def fs_read(body: FilesystemRequest, request: Request) -> Any:
    return await _fs_call(
        request, "read",
        {"path": body.path, "component_id": body.component_id, "session_id": body.session_id},
    )


@router.post("/filesystem/stat")
async def fs_stat(body: FilesystemRequest, request: Request) -> Any:
    return await _fs_call(
        request, "stat",
        {"path": body.path, "component_id": body.component_id, "session_id": body.session_id},
    )


@router.post("/filesystem/write")
async def fs_write(body: FilesystemRequest, request: Request) -> Any:
    return await _fs_call(
        request, "write",
        {
            "path": body.path,
            "content": body.content,
            "create_parents": body.create_parents,
            "component_id": body.component_id,
            "session_id": body.session_id,
        },
    )


@router.post("/filesystem/create")
async def fs_create(body: FilesystemRequest, request: Request) -> Any:
    return await _fs_call(
        request, "create",
        {
            "path": body.path,
            "is_dir": body.is_dir,
            "component_id": body.component_id,
            "session_id": body.session_id,
        },
    )


@router.post("/filesystem/delete")
async def fs_delete(body: FilesystemRequest, request: Request) -> Any:
    return await _fs_call(
        request, "delete",
        {
            "path": body.path,
            "recursive": body.recursive,
            "component_id": body.component_id,
            "session_id": body.session_id,
        },
    )


@router.post("/filesystem/move")
async def fs_move(body: FilesystemRequest, request: Request) -> Any:
    return await _fs_call(
        request, "move",
        {
            "src": body.src,
            "dest": body.dest,
            "component_id": body.component_id,
            "session_id": body.session_id,
        },
    )


# ── Browser ───────────────────────────────────────────────────────────────────


@router.post("/browser")
async def execute_browser(body: BrowserRequest, request: Request) -> Any:
    """Execute a browser automation operation."""
    from harness.tools.exceptions import ConfirmationRequired

    params: dict[str, Any] = {"operation": body.operation}
    if body.url:
        params["url"] = body.url
    if body.selector:
        params["selector"] = body.selector
    if body.value:
        params["value"] = body.value
    if body.expression:
        params["expression"] = body.expression
    if body.full_page:
        params["full_page"] = body.full_page

    try:
        result = await _mp(request).tools.execute(
            tool_name="browser",
            component_id=body.component_id,
            session_id=body.session_id,
            params=params,
        )
        return result.to_dict(redact_secrets=True)
    except ConfirmationRequired as exc:
        return _confirmation_response(exc)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── Database ──────────────────────────────────────────────────────────────────


@router.post("/database")
async def execute_database(body: DatabaseRequest, request: Request) -> Any:
    """Execute a database inspection or query operation."""
    from harness.tools.exceptions import ConfirmationRequired

    params: dict[str, Any] = {
        "operation": body.operation,
        "sql": body.sql,
        "params": body.params,
    }

    try:
        result = await _mp(request).tools.execute(
            tool_name="database",
            component_id=body.component_id,
            session_id=body.session_id,
            params=params,
        )
        return result.to_dict(redact_secrets=True)
    except ConfirmationRequired as exc:
        return _confirmation_response(exc)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── Confirmation ──────────────────────────────────────────────────────────────


@router.post("/confirm/{token}")
async def confirm_action(token: str, request: Request) -> dict[str, Any]:
    """Execute a confirmed destructive action by token."""
    import os

    import httpx
    ai_url = os.environ.get("RUST_BASE_AI_URL", "")
    if ai_url:
        rust_url = ai_url.rsplit("/v1", 1)[0]
        async with httpx.AsyncClient() as client:
            res = await client.post(f"{rust_url}/harness/tools/confirmations/{token}")
            if res.status_code == 200:
                return res.json()
            else:
                raise HTTPException(status_code=res.status_code, detail=res.text)

    store = _mp(request).tools.confirmations
    pending = store.get(token)
    if pending is None:
        raise HTTPException(status_code=404, detail="Confirmation token not found or expired.")

    # Re-execute the original action with the token embedded in params
    params = dict(pending.action_params)
    params["_confirmation_token"] = token

    from harness.tools.exceptions import ConfirmationRequired

    try:
        result = await _mp(request).tools.execute(
            tool_name="filesystem" if pending.action_name in ("delete", "move", "write") else "terminal",
            component_id=params.pop("component_id", None),
            session_id=params.pop("session_id", None),
            params={"operation": pending.action_name, **params}
            if pending.action_name in ("delete", "move", "write")
            else params,
        )
        return result.to_dict()
    except ConfirmationRequired:
        # Should not re-raise since we embedded the token; treat as error
        raise HTTPException(status_code=500, detail="Confirmation loop detected.")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/confirm/{token}", status_code=204)
async def cancel_confirmation(token: str, request: Request) -> None:
    """Cancel a pending confirmation without executing the action."""
    import os

    import httpx
    ai_url = os.environ.get("RUST_BASE_AI_URL", "")
    if ai_url:
        rust_url = ai_url.rsplit("/v1", 1)[0]
        async with httpx.AsyncClient() as client:
            await client.delete(f"{rust_url}/harness/tools/confirmations/{token}")
            return

    store = _mp(request).tools.confirmations
    store.cancel(token)


# ── Rollback ───────────────────────────────────────────────────────────────────


@router.post("/rollback/list")
async def list_rollbacks(body: RollbackRequest, request: Request) -> list[dict[str, Any]]:
    """List available backups for a file."""
    from harness.core.rollback import RollbackManager

    rollback = RollbackManager()
    file_path = Path(body.path)
    return rollback.list_backups(file_path)


@router.post("/rollback/execute")
async def execute_rollback(body: RollbackRequest, request: Request) -> dict[str, Any]:
    """Rollback a file to a previous backup."""
    from harness.core.rollback import RollbackManager

    rollback = RollbackManager()
    file_path = Path(body.path)
    success = rollback.rollback_file(file_path, backup_index=body.backup_index)

    if success:
        return {"success": True, "message": f"Rolled back {body.path} to backup {body.backup_index}"}
    else:
        raise HTTPException(status_code=400, detail="Rollback failed. Check that the file has backups.")


@router.post("/rollback/cleanup")
async def cleanup_rollbacks(request: Request) -> dict[str, Any]:
    """Clean up old backups to save disk space."""
    from harness.core.rollback import RollbackManager

    rollback = RollbackManager()
    removed = rollback.cleanup_old_backups()
    total_size = rollback.get_backup_size()

    return {
        "removed_count": removed,
        "total_size_bytes": total_size,
        "total_size_mb": round(total_size / (1024 * 1024), 2),
    }
