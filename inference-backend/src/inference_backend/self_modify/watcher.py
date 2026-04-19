"""Hot-reload watcher using watchfiles."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Callable

import watchfiles
from ..telemetry.logger import get_logger

logger = get_logger(__name__)

_MODULES_DIR = Path(__file__).parent.parent.parent.parent.parent / "modules"
_PIPELINES_DIR = Path(__file__).parent.parent.parent.parent.parent / "pipelines"


async def watch_modules(on_change: Callable[[str, str], None]) -> None:
    """Watch the modules/ dir and call on_change(name, event) on changes."""
    _MODULES_DIR.mkdir(parents=True, exist_ok=True)
    async for changes in watchfiles.awatch(_MODULES_DIR):
        for change_type, path in changes:
            name = Path(path).stem
            logger.info("Module changed", name=name, change=str(change_type))
            on_change(name, str(change_type))


async def watch_pipelines(on_change: Callable[[str, str], None]) -> None:
    """Watch the pipelines/ dir and call on_change(name, event) on changes."""
    _PIPELINES_DIR.mkdir(parents=True, exist_ok=True)
    async for changes in watchfiles.awatch(_PIPELINES_DIR):
        for change_type, path in changes:
            name = Path(path).stem
            logger.info("Pipeline changed", name=name, change=str(change_type))
            on_change(name, str(change_type))
