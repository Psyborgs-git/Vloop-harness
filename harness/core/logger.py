"""Per-component structured log streams backed by structlog + rich."""

from __future__ import annotations

import logging
import sys
import uuid
from collections import deque
from enum import IntEnum
from pathlib import Path
from typing import Any
import contextvars

import structlog
from rich.console import Console
from rich.logging import RichHandler


# Context variable for correlation ID
_correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="")


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
    def add_correlation_id(logger, method_name, event_dict):
        """Add correlation ID to log entries."""
        correlation_id = _correlation_id.get()
        if correlation_id:
            event_dict["correlation_id"] = correlation_id
        return event_dict

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            add_correlation_id,
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
        from harness.core.secret_redaction import redact_any

        # Redact secrets from message and kwargs
        safe_message = redact_any(message)
        safe_kw = redact_any(kw)

        entry = {"level": level.name, "message": safe_message, "component": self.component_id, **safe_kw}
        self._buffer.append(entry)
        fn = getattr(self._log, level.name.lower(), self._log.info)
        fn(safe_message, **safe_kw)

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


# ── Correlation ID helpers ─────────────────────────────────────────────────────


def set_correlation_id(correlation_id: str | None = None) -> str:
    """Set the correlation ID for the current context.

    Args:
        correlation_id: Optional correlation ID. If None, generates a new UUID.

    Returns:
        The correlation ID that was set.
    """
    if correlation_id is None:
        correlation_id = str(uuid.uuid4())
    _correlation_id.set(correlation_id)
    return correlation_id


def get_correlation_id() -> str:
    """Get the current correlation ID.

    Returns:
        The current correlation ID, or empty string if not set.
    """
    return _correlation_id.get()


def clear_correlation_id() -> None:
    """Clear the correlation ID from the current context."""
    _correlation_id.set("")
