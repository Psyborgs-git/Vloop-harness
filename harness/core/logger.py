"""Per-component structured log streams backed by structlog + rich."""

from __future__ import annotations

import logging
import sys
from collections import deque
from enum import IntEnum
from pathlib import Path
from typing import Any

import structlog
from rich.console import Console
from rich.logging import RichHandler


class LogLevel(IntEnum):
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARN = logging.WARNING
    ERROR = logging.ERROR


_console = Console(stderr=True)


def _configure_stdlib() -> None:
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=_console, rich_tracebacks=True, markup=True)],
    )


def _build_structlog() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


_configure_stdlib()
_build_structlog()


class ComponentLogStream:
    """In-memory ring buffer for a single component's logs."""

    def __init__(self, component_id: str, maxlen: int = 2000) -> None:
        self.component_id = component_id
        self._buffer: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self._log = structlog.get_logger(component_id)

    def _record(self, level: LogLevel, message: str, **kw: Any) -> None:
        entry = {"level": level.name, "message": message, "component": self.component_id, **kw}
        self._buffer.append(entry)
        fn = getattr(self._log, level.name.lower(), self._log.info)
        fn(message, **kw)

    def debug(self, msg: str, **kw: Any) -> None:
        self._record(LogLevel.DEBUG, msg, **kw)

    def info(self, msg: str, **kw: Any) -> None:
        self._record(LogLevel.INFO, msg, **kw)

    def warn(self, msg: str, **kw: Any) -> None:
        self._record(LogLevel.WARN, msg, **kw)

    def error(self, msg: str, **kw: Any) -> None:
        self._record(LogLevel.ERROR, msg, **kw)

    def tail(self, n: int = 50) -> list[dict[str, Any]]:
        entries = list(self._buffer)
        return entries[-n:]

    def export(self, path: Path) -> None:
        import json

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as f:
            json.dump(list(self._buffer), f, indent=2, default=str)


class HarnessLogger:
    """Root logger. Owns one ComponentLogStream per component."""

    def __init__(self, log_dir: Path | None = None) -> None:
        self._streams: dict[str, ComponentLogStream] = {}
        self._log_dir = log_dir or Path(".harness/logs")
        self._root = structlog.get_logger("harness")

    def register(self, component_id: str) -> ComponentLogStream:
        stream = ComponentLogStream(component_id)
        self._streams[component_id] = stream
        return stream

    def unregister(self, component_id: str) -> None:
        self._streams.pop(component_id, None)

    def get(self, component_id: str) -> ComponentLogStream:
        if component_id not in self._streams:
            return self.register(component_id)
        return self._streams[component_id]

    def log(self, component_id: str, level: LogLevel, message: str, **kw: Any) -> None:
        self.get(component_id)._record(level, message, **kw)

    def tail(self, component_id: str, n: int = 50) -> list[dict[str, Any]]:
        return self.get(component_id).tail(n)

    def export(self, component_id: str, path: Path | None = None) -> None:
        dest = path or (self._log_dir / f"{component_id}.json")
        self.get(component_id).export(dest)

    def info(self, msg: str, **kw: Any) -> None:
        self._root.info(msg, **kw)

    def error(self, msg: str, **kw: Any) -> None:
        self._root.error(msg, **kw)
