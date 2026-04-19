"""file_rw tool — read or write files within the project root."""
from __future__ import annotations

import os
from pathlib import Path
from ..registry import tool

_PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", Path.cwd()))


def _safe_path(path_str: str) -> Path:
    p = (_PROJECT_ROOT / path_str).resolve()
    if not str(p).startswith(str(_PROJECT_ROOT.resolve())):
        raise ValueError(f"Path escape: {path_str!r}")
    return p


@tool("file_rw")
def file_rw(path: str, mode: str = "read", content: str = "") -> dict:
    """Read or write a file. mode='read' or mode='write'."""
    try:
        safe = _safe_path(path)
        if mode == "read":
            return {"content": safe.read_text(encoding="utf-8")}
        elif mode == "write":
            safe.parent.mkdir(parents=True, exist_ok=True)
            safe.write_text(content, encoding="utf-8")
            return {"status": "ok", "path": str(safe)}
        else:
            return {"error": f"Unknown mode: {mode}"}
    except Exception as exc:
        return {"error": str(exc)}
