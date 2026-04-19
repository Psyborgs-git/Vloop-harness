"""shell_exec tool — run a shell command and return stdout/stderr."""
from __future__ import annotations

import subprocess
from ..registry import tool


@tool("shell_exec")
def shell_exec(command: str, timeout: int = 30, cwd: str | None = None) -> dict:
    """Execute a shell command safely."""
    try:
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
