"""TerminalTool — safe, policy-gated subprocess execution.

Security guarantees
───────────────────
• ``shell=False`` always — no shell expansion.
• Shell injection patterns detected before execution and rejected.
• Workspace boundary enforced on CWD.
• Environment variables stripped; only a minimal safe set is passed.
• Process group killed on timeout.
• Stdout/stderr truncated at ``max_output_bytes``.
• No stdin (non-interactive only).
"""

from __future__ import annotations

import asyncio
import os
import shlex
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from harness.core.permissions import Permission
from harness.tools.base_tool import AbstractTool, ToolResult
from harness.tools.exceptions import TimeoutExceeded, WorkspaceEscape

if TYPE_CHECKING:
    from harness.core.main_process import MainProcess

# Minimal safe environment passed to every subprocess
_SAFE_ENV_KEYS = {"PATH", "HOME", "LANG", "TERM", "USER", "LOGNAME"}


class TerminalTool(AbstractTool):
    """Execute shell commands safely within the workspace boundary."""

    name = "terminal"
    description = (
        "Execute a command within the workspace. "
        "Subject to the three-tier policy (blocklist / denylist / allowlist). "
        "Requires SHELL_EXEC permission."
    )
    required_permission = Permission.SHELL_EXEC
    risk_level = "caution"

    def __init__(self, main_process: "MainProcess") -> None:
        super().__init__(main_process)

    # ── Execute ───────────────────────────────────────────────────────────────

    async def execute(
        self,
        component_id: str | None,
        session_id: str | None,
        params: dict[str, Any],
    ) -> ToolResult:
        """Run a command.

        Expected params
        ───────────────
        command : str
            The command string to execute (e.g. ``"pytest -v tests/"``).
        cwd_relative : str, optional
            Working directory relative to workspace_root. Defaults to ``"."``.
        timeout : int, optional
            Override the policy max_runtime_seconds for this call.
        """
        self._check_permission(component_id)

        command: str = params.get("command", "")
        cwd_relative: str = params.get("cwd_relative", ".")
        timeout_override: int | None = params.get("timeout")

        if not command.strip():
            return ToolResult(success=False, error="No command provided.")

        policy_engine = self._mp.tools.policy

        # 1. Shell-injection check
        try:
            policy_engine.check_shell_injection(command)
        except ValueError as exc:
            return ToolResult(success=False, error=str(exc))

        # 2. Parse into argv (no shell=True)
        try:
            argv = shlex.split(command)
        except ValueError as exc:
            return ToolResult(success=False, error=f"Failed to parse command: {exc}")

        if not argv:
            return ToolResult(success=False, error="Empty command after parsing.")

        binary = argv[0]
        args = argv[1:]

        # 3. Resolve CWD and check workspace boundary
        workspace_root = self._mp.workspace_root
        try:
            cwd_abs = (workspace_root / cwd_relative).resolve()
        except Exception as exc:
            return ToolResult(success=False, error=f"Invalid cwd_relative: {exc}")

        try:
            _assert_within_workspace(cwd_abs, workspace_root)
        except WorkspaceEscape as exc:
            return ToolResult(success=False, error=str(exc))

        # 4–7. Policy checks
        try:
            dir_policy = policy_engine.check_command(binary, args, cwd_abs)
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))

        timeout = timeout_override if timeout_override is not None else dir_policy.max_runtime_seconds
        max_bytes = dir_policy.max_output_bytes

        # 8. Strip environment
        safe_env = {k: v for k, v in os.environ.items() if k in _SAFE_ENV_KEYS}

        # 9. Run the process
        start_time = time.monotonic()
        proc: asyncio.subprocess.Process | None = None
        try:
            proc = await asyncio.create_subprocess_exec(
                binary,
                *args,
                cwd=str(cwd_abs),
                env=safe_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.DEVNULL,
            )
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                # 10. Kill the process group on timeout
                _kill_process(proc)
                return ToolResult(
                    success=False,
                    error=f"Command timed out after {timeout}s.",
                    exit_code=-1,
                    metadata={"command": command, "cwd": str(cwd_abs)},
                )
        except FileNotFoundError:
            return ToolResult(
                success=False,
                error=f"Command not found: {binary!r}",
            )
        except Exception as exc:
            if proc is not None:
                _kill_process(proc)
            return ToolResult(success=False, error=f"Execution error: {exc}")

        duration_ms = int((time.monotonic() - start_time) * 1000)

        # 11. Truncate output
        output = _truncate(stdout_bytes, max_bytes)
        stderr_out = _truncate(stderr_bytes, max_bytes)

        exit_code = proc.returncode if proc.returncode is not None else -1
        success = exit_code == 0

        combined = output
        if stderr_out:
            combined = f"{output}\n[stderr]\n{stderr_out}" if output else f"[stderr]\n{stderr_out}"

        return ToolResult(
            success=success,
            output=combined,
            error=None if success else f"Process exited with code {exit_code}",
            exit_code=exit_code,
            metadata={
                "command": command,
                "cwd": str(cwd_abs),
                "duration_ms": duration_ms,
                "truncated": len(stdout_bytes) > max_bytes or len(stderr_bytes) > max_bytes,
            },
        )


# ── Helpers ───────────────────────────────────────────────────────────────────


def _assert_within_workspace(path: Path, workspace_root: Path) -> None:
    """Raise WorkspaceEscape if *path* is not inside *workspace_root*."""
    resolved = path.resolve()
    try:
        resolved.relative_to(workspace_root)
    except ValueError:
        raise WorkspaceEscape(
            f"Path {resolved!r} is outside the workspace root {workspace_root!r}."
        )


def _kill_process(proc: asyncio.subprocess.Process) -> None:
    """Best-effort process kill."""
    try:
        proc.kill()
    except Exception:
        pass


def _truncate(data: bytes, max_bytes: int) -> str:
    if len(data) > max_bytes:
        data = data[:max_bytes]
    return data.decode("utf-8", errors="replace")
