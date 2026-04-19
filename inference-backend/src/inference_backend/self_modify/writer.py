"""Atomic writer for agent-generated Python files."""
from __future__ import annotations

import os
from pathlib import Path

from ..telemetry.logger import get_logger

logger = get_logger(__name__)

_MODULES_DIR = Path(__file__).parent.parent.parent.parent.parent / "modules"
_PIPELINES_DIR = Path(__file__).parent.parent.parent.parent.parent / "pipelines"


def write_module(name: str, code: str) -> Path:
    """Atomically write agent-generated module code to modules/<name>.py."""
    _MODULES_DIR.mkdir(parents=True, exist_ok=True)
    target = _MODULES_DIR / f"{name}.py"
    tmp = target.with_suffix(".tmp")
    try:
        tmp.write_text(code, encoding="utf-8")
        os.replace(tmp, target)
        logger.info("Module written", name=name, path=str(target))
        return target
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def write_pipeline(name: str, code: str) -> Path:
    """Atomically write pipeline code to pipelines/<name>.py."""
    _PIPELINES_DIR.mkdir(parents=True, exist_ok=True)
    target = _PIPELINES_DIR / f"{name}.py"
    tmp = target.with_suffix(".tmp")
    try:
        tmp.write_text(code, encoding="utf-8")
        os.replace(tmp, target)
        logger.info("Pipeline written", name=name, path=str(target))
        return target
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
