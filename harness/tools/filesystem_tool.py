"""FilesystemTool — safe, policy-gated file and directory operations.

All paths are resolved and verified to be inside the workspace root before
any I/O is attempted. Destructive operations (delete, move, overwrite-write)
require human confirmation via the ConfirmationStore.
"""

from __future__ import annotations

import base64
import os
import shutil
import stat
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from harness.core.permissions import Permission
from harness.tools.base_tool import AbstractTool, ToolResult
from harness.tools.exceptions import ConfirmationRequired, WorkspaceEscape

if TYPE_CHECKING:
    from harness.core.main_process import MainProcess

# Binary file detection threshold
_BINARY_SNIFF_BYTES = 8192
_TEXT_READ_MAX_BYTES = 1 * 1024 * 1024  # 1 MiB


class FilesystemTool(AbstractTool):
    """File and directory operations bounded to the workspace root."""

    name = "filesystem"
    description = (
        "File and directory operations (list, read, stat, write, create, delete, move) "
        "within the workspace. Destructive operations require confirmation."
    )
    required_permission = Permission.FILESYSTEM_READ  # minimum; write ops checked inline
    risk_level = "safe"

    def __init__(self, main_process: "MainProcess") -> None:
        super().__init__(main_process)
        from harness.core.rollback import RollbackManager
        self._rollback = RollbackManager()

    # ── Dispatch ──────────────────────────────────────────────────────────────

    async def execute(
        self,
        component_id: str | None,
        session_id: str | None,
        params: dict[str, Any],
    ) -> ToolResult:
        """Dispatch to a sub-operation based on ``params["operation"]``."""
        self._check_permission(component_id)

        operation: str = params.get("operation", "")
        op_map = {
            "list": self._list,
            "read": self._read,
            "stat": self._stat,
            "write": self._write,
            "create": self._create,
            "delete": self._delete,
            "move": self._move,
        }
        handler = op_map.get(operation)
        if handler is None:
            return ToolResult(
                success=False,
                error=f"Unknown filesystem operation: {operation!r}. "
                      f"Valid: {list(op_map)!r}",
            )
        return await handler(component_id, params)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _resolve(self, rel_path: str) -> Path:
        """Resolve *rel_path* against workspace_root and assert boundary."""
        workspace = self._mp.workspace_root
        abs_path = (workspace / rel_path).resolve()
        try:
            abs_path.relative_to(workspace)
        except ValueError:
            raise WorkspaceEscape(
                f"Path {rel_path!r} resolves to {abs_path!r} which is outside "
                f"the workspace root {workspace!r}."
            )
        return abs_path

    def _require_write(self, component_id: str | None) -> None:
        from harness.tools.exceptions import PermissionDenied

        cid = component_id or "root"
        if cid == "root":
            return
        if not self._mp.permissions.has(cid, Permission.FILESYSTEM_WRITE):
            raise PermissionDenied(
                f"Component {cid!r} does not have FILESYSTEM_WRITE permission."
            )

    # ── Operations ────────────────────────────────────────────────────────────

    async def _list(self, _component_id: str | None, params: dict[str, Any]) -> ToolResult:
        rel_path = params.get("path", ".")
        try:
            abs_path = self._resolve(rel_path)
        except WorkspaceEscape as exc:
            return ToolResult(success=False, error=str(exc))

        if not abs_path.exists():
            return ToolResult(success=False, error=f"Path does not exist: {rel_path!r}")
        if not abs_path.is_dir():
            return ToolResult(success=False, error=f"Not a directory: {rel_path!r}")

        entries = []
        try:
            for entry in sorted(abs_path.iterdir(), key=lambda e: (e.is_file(), e.name)):
                try:
                    s = entry.stat()
                    entries.append(
                        {
                            "name": entry.name,
                            "type": "dir" if entry.is_dir() else "file",
                            "size": s.st_size if entry.is_file() else None,
                            "mtime": s.st_mtime,
                        }
                    )
                except OSError:
                    entries.append({"name": entry.name, "type": "unknown"})
        except PermissionError as exc:
            return ToolResult(success=False, error=f"Permission denied: {exc}")

        return ToolResult(
            success=True,
            output="",
            metadata={"path": str(abs_path), "entries": entries},
        )

    async def _read(self, _component_id: str | None, params: dict[str, Any]) -> ToolResult:
        rel_path = params.get("path", "")
        if not rel_path:
            return ToolResult(success=False, error="No path provided.")
        try:
            abs_path = self._resolve(rel_path)
        except WorkspaceEscape as exc:
            return ToolResult(success=False, error=str(exc))

        if not abs_path.exists():
            return ToolResult(success=False, error=f"File not found: {rel_path!r}")
        if abs_path.is_dir():
            return ToolResult(success=False, error=f"Path is a directory: {rel_path!r}")

        try:
            raw = abs_path.read_bytes()
        except OSError as exc:
            return ToolResult(success=False, error=f"Read error: {exc}")

        # Detect binary by checking for null bytes in the sniff window
        is_binary = b"\x00" in raw[:_BINARY_SNIFF_BYTES]
        if is_binary:
            truncated = len(raw) > _TEXT_READ_MAX_BYTES
            chunk = raw[:_TEXT_READ_MAX_BYTES]
            content = base64.b64encode(chunk).decode("ascii")
            return ToolResult(
                success=True,
                output=content,
                metadata={
                    "path": str(abs_path),
                    "encoding": "base64",
                    "size": len(raw),
                    "truncated": truncated,
                },
            )
        else:
            truncated = len(raw) > _TEXT_READ_MAX_BYTES
            text = raw[:_TEXT_READ_MAX_BYTES].decode("utf-8", errors="replace")
            return ToolResult(
                success=True,
                output=text,
                metadata={
                    "path": str(abs_path),
                    "encoding": "utf-8",
                    "size": len(raw),
                    "truncated": truncated,
                },
            )

    async def _stat(self, _component_id: str | None, params: dict[str, Any]) -> ToolResult:
        rel_path = params.get("path", "")
        if not rel_path:
            return ToolResult(success=False, error="No path provided.")
        try:
            abs_path = self._resolve(rel_path)
        except WorkspaceEscape as exc:
            return ToolResult(success=False, error=str(exc))

        if not abs_path.exists():
            return ToolResult(success=False, error=f"Path not found: {rel_path!r}")
        try:
            s = abs_path.stat()
        except OSError as exc:
            return ToolResult(success=False, error=f"Stat error: {exc}")

        return ToolResult(
            success=True,
            metadata={
                "path": str(abs_path),
                "type": "dir" if abs_path.is_dir() else "file",
                "size": s.st_size,
                "mtime": s.st_mtime,
                "mode": stat.filemode(s.st_mode),
            },
        )

    async def _write(self, component_id: str | None, params: dict[str, Any]) -> ToolResult:
        try:
            self._require_write(component_id)
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))

        rel_path = params.get("path", "")
        content: str = params.get("content", "")
        create_parents: bool = params.get("create_parents", False)

        if not rel_path:
            return ToolResult(success=False, error="No path provided.")
        try:
            abs_path = self._resolve(rel_path)
        except WorkspaceEscape as exc:
            return ToolResult(success=False, error=str(exc))

        overwriting = abs_path.exists() and abs_path.is_file()
        if overwriting:
            # Generate diff preview for overwrites
            from harness.core.diff_utils import generate_file_diff, diff_summary

            diff = generate_file_diff(abs_path, content)
            summary = diff_summary(diff)

            # Create backup before overwrite
            backup_info = self._rollback.backup_file(abs_path)

            # Require confirmation for overwrite
            conf_store = self._mp.tools.confirmations
            confirmation_token = params.get("_confirmation_token")
            if confirmation_token:
                # Validate the token
                try:
                    conf_store.confirm(confirmation_token)
                except (KeyError, TimeoutError) as exc:
                    return ToolResult(success=False, error=f"Invalid confirmation token: {exc}")
            else:
                pending = conf_store.create(
                    description=f"Overwrite existing file: {rel_path} ({summary['total_changes']} lines changed)",
                    risk_level="caution",
                    action_name="write",
                    action_params={**params, "_diff_preview": diff, "_diff_summary": summary, "_backup_info": backup_info},
                )
                raise ConfirmationRequired(
                    token=pending.token,
                    description=pending.description,
                    risk_level=pending.risk_level,
                )

        try:
            if create_parents:
                abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_text(content, encoding="utf-8")
        except OSError as exc:
            return ToolResult(success=False, error=f"Write error: {exc}")

        return ToolResult(
            success=True,
            metadata={"path": str(abs_path), "bytes_written": len(content.encode())},
        )

    async def _create(self, component_id: str | None, params: dict[str, Any]) -> ToolResult:
        try:
            self._require_write(component_id)
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))

        rel_path = params.get("path", "")
        is_dir: bool = params.get("is_dir", False)

        if not rel_path:
            return ToolResult(success=False, error="No path provided.")
        try:
            abs_path = self._resolve(rel_path)
        except WorkspaceEscape as exc:
            return ToolResult(success=False, error=str(exc))

        if abs_path.exists():
            return ToolResult(
                success=False,
                error=f"Path already exists: {rel_path!r}",
            )

        try:
            if is_dir:
                abs_path.mkdir(parents=True, exist_ok=False)
            else:
                abs_path.parent.mkdir(parents=True, exist_ok=True)
                abs_path.touch()
        except OSError as exc:
            return ToolResult(success=False, error=f"Create error: {exc}")

        return ToolResult(
            success=True,
            metadata={"path": str(abs_path), "type": "dir" if is_dir else "file"},
        )

    async def _delete(self, component_id: str | None, params: dict[str, Any]) -> ToolResult:
        try:
            self._require_write(component_id)
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))

        rel_path = params.get("path", "")
        recursive: bool = params.get("recursive", False)

        if not rel_path:
            return ToolResult(success=False, error="No path provided.")
        try:
            abs_path = self._resolve(rel_path)
        except WorkspaceEscape as exc:
            return ToolResult(success=False, error=str(exc))

        if not abs_path.exists():
            return ToolResult(success=False, error=f"Path not found: {rel_path!r}")

        # Always require confirmation for delete
        conf_store = self._mp.tools.confirmations
        confirmation_token = params.get("_confirmation_token")
        if confirmation_token:
            try:
                conf_store.confirm(confirmation_token)
            except (KeyError, TimeoutError) as exc:
                return ToolResult(success=False, error=f"Invalid confirmation token: {exc}")
        else:
            kind = "directory tree" if abs_path.is_dir() else "file"
            pending = conf_store.create(
                description=f"Permanently delete {kind}: {rel_path}",
                risk_level="destructive",
                action_name="delete",
                action_params=params,
            )
            raise ConfirmationRequired(
                token=pending.token,
                description=pending.description,
                risk_level=pending.risk_level,
            )

        try:
            if abs_path.is_dir():
                if recursive:
                    shutil.rmtree(abs_path)
                else:
                    abs_path.rmdir()
            else:
                abs_path.unlink()
        except OSError as exc:
            return ToolResult(success=False, error=f"Delete error: {exc}")

        return ToolResult(
            success=True,
            metadata={"path": str(abs_path), "recursive": recursive},
        )

    async def _move(self, component_id: str | None, params: dict[str, Any]) -> ToolResult:
        try:
            self._require_write(component_id)
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))

        src_rel = params.get("src", "")
        dest_rel = params.get("dest", "")

        if not src_rel or not dest_rel:
            return ToolResult(success=False, error="Both 'src' and 'dest' are required.")
        try:
            src_abs = self._resolve(src_rel)
            dest_abs = self._resolve(dest_rel)
        except WorkspaceEscape as exc:
            return ToolResult(success=False, error=str(exc))

        if not src_abs.exists():
            return ToolResult(success=False, error=f"Source not found: {src_rel!r}")

        # Always require confirmation for move/rename
        conf_store = self._mp.tools.confirmations
        confirmation_token = params.get("_confirmation_token")
        if confirmation_token:
            try:
                conf_store.confirm(confirmation_token)
            except (KeyError, TimeoutError) as exc:
                return ToolResult(success=False, error=f"Invalid confirmation token: {exc}")
        else:
            pending = conf_store.create(
                description=f"Move {src_rel!r} → {dest_rel!r}",
                risk_level="destructive",
                action_name="move",
                action_params=params,
            )
            raise ConfirmationRequired(
                token=pending.token,
                description=pending.description,
                risk_level=pending.risk_level,
            )

        try:
            shutil.move(str(src_abs), str(dest_abs))
        except OSError as exc:
            return ToolResult(success=False, error=f"Move error: {exc}")

        return ToolResult(
            success=True,
            metadata={"src": str(src_abs), "dest": str(dest_abs)},
        )
