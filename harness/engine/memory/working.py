"""WorkingMemory — short-term scratchpad for agent runs and pipelines."""

from __future__ import annotations

from typing import Any


class WorkingMemory:
    """A key-value scratchpad shared across an agent run or pipeline execution.

    Provides typed accessors and structured data helpers.
    """

    def __init__(self, initial: dict[str, Any] | None = None) -> None:
        self._store: dict[str, Any] = dict(initial or {})

    # ── Core API ──────────────────────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        return self._store.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._store[key] = value

    def delete(self, key: str) -> bool:
        if key in self._store:
            del self._store[key]
            return True
        return False

    def has(self, key: str) -> bool:
        return key in self._store

    def clear(self) -> None:
        self._store.clear()

    def all(self) -> dict[str, Any]:
        return dict(self._store)

    # ── Typed helpers ─────────────────────────────────────────────────────────

    def get_str(self, key: str, default: str = "") -> str:
        val = self._store.get(key, default)
        return str(val) if val is not None else default

    def get_int(self, key: str, default: int = 0) -> int:
        try:
            return int(self._store.get(key, default))
        except (TypeError, ValueError):
            return default

    def get_float(self, key: str, default: float = 0.0) -> float:
        try:
            return float(self._store.get(key, default))
        except (TypeError, ValueError):
            return default

    def get_list(self, key: str, default: list[Any] | None = None) -> list[Any]:
        val = self._store.get(key, default or [])
        if isinstance(val, list):
            return val
        return [val]

    def append(self, key: str, value: Any) -> None:
        if key not in self._store:
            self._store[key] = []
        if not isinstance(self._store[key], list):
            self._store[key] = [self._store[key]]
        self._store[key].append(value)

    def merge(self, other: dict[str, Any]) -> None:
        self._store.update(other)

    # ── Context window helpers ──────────────────────────────────────────────────

    def token_estimate(self) -> int:
        """Rough token estimate of all stored string values."""
        total = 0
        for v in self._store.values():
            if isinstance(v, str):
                total += max(1, len(v) // 4)
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, str):
                        total += max(1, len(item) // 4)
        return total
