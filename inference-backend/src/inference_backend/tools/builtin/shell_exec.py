"""shell_exec tool — run a shell command and return stdout/stderr."""
from __future__ import annotations

import os
import subprocess
from ..registry import tool

# When SANDBOX_MODE=strict, shell execution via shell=True is disabled.
# Agents receive a clear error rather than silently being allowed to run
# unrestricted shell pipelines.  Individual sub-processes (list form) are
# still permitted so structured tool calls continue to work.
_SANDBOX_MODE: str = os.getenv("SANDBOX_MODE", "permissive").lower()
_STRICT: bool = _SANDBOX_MODE == "strict"


@tool("shell_exec")
def shell_exec(command: str, timeout: int = 30, cwd: str | None = None) -> dict:
    """Execute a shell command safely.

    In strict sandbox mode (``SANDBOX_MODE=strict``) the command is split into
    a token list and executed without a shell interpreter, preventing pipeline
    chaining, variable injection, and other shell-expansion exploits.
    """
    try:
        if _STRICT:
            import shlex
            args = shlex.split(command)
            result = subprocess.run(
                args,
                shell=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
            )
        else:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
            )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": "Command timed out", "returncode": -1}
    except Exception as exc:
        return {"error": str(exc), "returncode": -1}
