from __future__ import annotations

from typing import Any, Callable


class ToolRegistry:
    _tools: dict[str, Callable] = {}

    @classmethod
    def register(cls, name: str, fn: Callable) -> None:
        cls._tools[name] = fn

    @classmethod
    def get(cls, name: str) -> Callable | None:
        return cls._tools.get(name)

    @classmethod
    def list(cls) -> list[str]:
        return list(cls._tools.keys())

    @classmethod
    def get_all_callables(cls) -> list[Callable]:
        return list(cls._tools.values())


def tool(name: str):
    """Decorator to register a function as a tool."""
    def decorator(fn: Callable) -> Callable:
        ToolRegistry.register(name, fn)
        fn.tool_name = name  # type: ignore[attr-defined]
        return fn
    return decorator


# Auto-register builtins on import
from .builtin import shell_exec, file_rw, http_request, db_query  # noqa: E402, F401
