"""StateStore — async SQLite-backed state persistence for all components."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiosqlite


class StateStore:
    """
    Persists component state across restarts using aiosqlite.

    Schema: (component_id TEXT, key TEXT, value TEXT, PRIMARY KEY (component_id, key))
    """

    def __init__(self, db_path: Path | str = ".harness/state.db") -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db: aiosqlite.Connection | None = None
        self._memory: dict[str, dict[str, Any]] = {}

    async def open(self) -> None:
        self._db = await aiosqlite.connect(str(self._db_path))
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS state (
                component_id TEXT NOT NULL,
                key          TEXT NOT NULL,
                value        TEXT NOT NULL,
                PRIMARY KEY (component_id, key)
            )
            """
        )
        await self._db.commit()
        await self.restore()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    # ── Read/Write ────────────────────────────────────────────────────────────

    async def set(self, component_id: str, key: str, value: Any) -> None:
        if component_id not in self._memory:
            self._memory[component_id] = {}
        self._memory[component_id][key] = value
        if self._db:
            await self._db.execute(
                "INSERT OR REPLACE INTO state (component_id, key, value) VALUES (?, ?, ?)",
                (component_id, key, json.dumps(value, default=str)),
            )
            await self._db.commit()

    async def get(self, component_id: str, key: str, default: Any = None) -> Any:
        return self._memory.get(component_id, {}).get(key, default)

    async def get_all(self, component_id: str) -> dict[str, Any]:
        return dict(self._memory.get(component_id, {}))

    async def flush(self, component_id: str) -> None:
        self._memory.pop(component_id, None)
        if self._db:
            await self._db.execute(
                "DELETE FROM state WHERE component_id = ?", (component_id,)
            )
            await self._db.commit()

    # ── Bulk ops ──────────────────────────────────────────────────────────────

    async def persist(self) -> None:
        """Flush in-memory state to disk."""
        if not self._db:
            return
        rows = [
            (cid, key, json.dumps(val, default=str))
            for cid, kv in self._memory.items()
            for key, val in kv.items()
        ]
        await self._db.executemany(
            "INSERT OR REPLACE INTO state (component_id, key, value) VALUES (?, ?, ?)", rows
        )
        await self._db.commit()

    async def restore(self) -> None:
        """Load all persisted state from disk into memory."""
        if not self._db:
            return
        async with self._db.execute("SELECT component_id, key, value FROM state") as cur:
            async for row in cur:
                cid, key, raw = row
                if cid not in self._memory:
                    self._memory[cid] = {}
                try:
                    self._memory[cid][key] = json.loads(raw)
                except json.JSONDecodeError:
                    self._memory[cid][key] = raw
