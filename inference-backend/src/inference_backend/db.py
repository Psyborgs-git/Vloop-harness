"""Database layer for inference-backend agent run persistence.

Two backends are supported, selected via ``DB_ENGINE``:

* **harness-core** (default, ``DB_ENGINE != 'postgres'``): posts SQL to the
  harness-core internal REST API at :47200/api/db/query.  Agent run data lands
  in the same SQLite that the Tauri UI reads via IPC — so the run history panel
  always reflects the live state without any extra synchronisation.

* **postgres** (``DB_ENGINE=postgres``): writes directly to Postgres through
  SQLAlchemy async (asyncpg driver).  Requires ``POSTGRES_URL`` to be set.
  The schema is created automatically on startup.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from .config import DB_ENGINE, HARNESS_CORE_URL
from .telemetry.logger import get_logger

logger = get_logger(__name__)

POSTGRES_URL: str = os.getenv("POSTGRES_URL", "")

# --------------------------------------------------------------------------- #
# Schema (Postgres path only — SQLite schema is owned by harness-core)        #
# --------------------------------------------------------------------------- #

_CREATE_TABLES_PG = [
    """
    CREATE TABLE IF NOT EXISTS agent_runs (
        id TEXT PRIMARY KEY,
        agent_name TEXT NOT NULL,
        agent_loop TEXT NOT NULL,
        task TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        finished_at TEXT,
        config_json TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_steps (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        step_index INTEGER NOT NULL,
        step_type TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tool_calls (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        step_id TEXT,
        tool_name TEXT NOT NULL,
        inputs_json TEXT NOT NULL,
        outputs_json TEXT,
        status TEXT NOT NULL,
        duration_ms INTEGER,
        created_at TEXT NOT NULL
    )
    """,
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# Abstract base                                                                #
# --------------------------------------------------------------------------- #

class AgentDB(ABC):
    """Minimal persistence interface for agent run data."""

    async def init(self) -> None:
        """Optional initialisation (called once at startup)."""

    @abstractmethod
    async def insert_agent_run(
        self,
        run_id: str,
        agent_loop: str,
        task: str,
        config_json: str | None = None,
    ) -> None: ...

    @abstractmethod
    async def finish_agent_run(self, run_id: str, status: str) -> None: ...

    @abstractmethod
    async def insert_agent_step(
        self,
        step_id: str,
        run_id: str,
        step_index: int,
        step_type: str,
        content: str,
    ) -> None: ...

    @abstractmethod
    async def insert_tool_call(
        self,
        call_id: str,
        run_id: str,
        step_id: str | None,
        tool_name: str,
        inputs_json: str,
        outputs_json: str | None,
        status: str,
        duration_ms: int | None,
    ) -> None: ...


# --------------------------------------------------------------------------- #
# HarnessCoreDB — forwards SQL to harness-core REST API                       #
# --------------------------------------------------------------------------- #

class HarnessCoreDB(AgentDB):
    """Persists via ``POST /api/db/query`` on harness-core (:47200).

    This keeps a single SQLite owner (harness-core) so the Tauri IPC layer
    can read agent history without any extra synchronisation.  Failures are
    logged but never raised — a DB write failure must not abort an agent run.
    """

    async def _execute(self, sql: str, params: list[Any]) -> None:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    f"{HARNESS_CORE_URL}/api/db/query",
                    json={"sql": sql, "params": params},
                )
                resp.raise_for_status()
        except Exception as exc:
            logger.warning(
                "DB execute skipped (harness-core unavailable)",
                sql=sql[:80],
                error=str(exc),
            )

    async def insert_agent_run(
        self,
        run_id: str,
        agent_loop: str,
        task: str,
        config_json: str | None = None,
    ) -> None:
        await self._execute(
            "INSERT OR IGNORE INTO agent_runs "
            "(id, agent_name, agent_loop, task, status, created_at, config_json) "
            "VALUES (?, ?, ?, ?, 'running', ?, ?)",
            [run_id, agent_loop, agent_loop, task, _now(), config_json],
        )

    async def finish_agent_run(self, run_id: str, status: str) -> None:
        await self._execute(
            "UPDATE agent_runs SET status = ?, finished_at = ? WHERE id = ?",
            [status, _now(), run_id],
        )

    async def insert_agent_step(
        self,
        step_id: str,
        run_id: str,
        step_index: int,
        step_type: str,
        content: str,
    ) -> None:
        await self._execute(
            "INSERT OR IGNORE INTO agent_steps "
            "(id, run_id, step_index, step_type, content, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [step_id, run_id, step_index, step_type, content, _now()],
        )

    async def insert_tool_call(
        self,
        call_id: str,
        run_id: str,
        step_id: str | None,
        tool_name: str,
        inputs_json: str,
        outputs_json: str | None,
        status: str,
        duration_ms: int | None,
    ) -> None:
        await self._execute(
            "INSERT OR IGNORE INTO tool_calls "
            "(id, run_id, step_id, tool_name, inputs_json, "
            " outputs_json, status, duration_ms, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                call_id,
                run_id,
                step_id,
                tool_name,
                inputs_json,
                outputs_json,
                status,
                duration_ms,
                _now(),
            ],
        )


# --------------------------------------------------------------------------- #
# PostgresDB — direct async Postgres via SQLAlchemy + asyncpg                 #
# --------------------------------------------------------------------------- #

class PostgresDB(AgentDB):
    """Persists directly to Postgres using SQLAlchemy async (asyncpg driver).

    Requires: ``pip install sqlalchemy asyncpg``
    Activated by: ``DB_ENGINE=postgres`` + ``POSTGRES_URL=postgresql://...``
    """

    def __init__(self) -> None:
        self._engine: Any = None

    async def init(self) -> None:
        try:
            from sqlalchemy.ext.asyncio import create_async_engine
            from sqlalchemy import text
        except ImportError as exc:
            raise RuntimeError(
                "PostgresDB requires: pip install sqlalchemy asyncpg"
            ) from exc

        url = (
            POSTGRES_URL
            .replace("postgresql://", "postgresql+asyncpg://")
            .replace("postgres://", "postgresql+asyncpg://")
        )
        self._engine = create_async_engine(url, pool_pre_ping=True)

        async with self._engine.begin() as conn:
            for stmt in _CREATE_TABLES_PG:
                await conn.execute(text(stmt.strip()))

        logger.info("PostgresDB initialised", url=url.split("@")[-1])

    async def _exec(self, sql: str, params: dict[str, Any]) -> None:
        from sqlalchemy import text

        try:
            async with self._engine.begin() as conn:
                await conn.execute(text(sql), params)
        except Exception as exc:
            logger.warning("Postgres execute failed", sql=sql[:80], error=str(exc))

    async def insert_agent_run(
        self,
        run_id: str,
        agent_loop: str,
        task: str,
        config_json: str | None = None,
    ) -> None:
        await self._exec(
            "INSERT INTO agent_runs "
            "(id, agent_name, agent_loop, task, status, created_at, config_json) "
            "VALUES (:id, :agent_name, :agent_loop, :task, 'running', :created_at, :config_json) "
            "ON CONFLICT (id) DO NOTHING",
            {
                "id": run_id,
                "agent_name": agent_loop,
                "agent_loop": agent_loop,
                "task": task,
                "created_at": _now(),
                "config_json": config_json,
            },
        )

    async def finish_agent_run(self, run_id: str, status: str) -> None:
        await self._exec(
            "UPDATE agent_runs SET status = :status, finished_at = :finished_at WHERE id = :id",
            {"status": status, "finished_at": _now(), "id": run_id},
        )

    async def insert_agent_step(
        self,
        step_id: str,
        run_id: str,
        step_index: int,
        step_type: str,
        content: str,
    ) -> None:
        await self._exec(
            "INSERT INTO agent_steps "
            "(id, run_id, step_index, step_type, content, created_at) "
            "VALUES (:id, :run_id, :step_index, :step_type, :content, :created_at) "
            "ON CONFLICT (id) DO NOTHING",
            {
                "id": step_id,
                "run_id": run_id,
                "step_index": step_index,
                "step_type": step_type,
                "content": content,
                "created_at": _now(),
            },
        )

    async def insert_tool_call(
        self,
        call_id: str,
        run_id: str,
        step_id: str | None,
        tool_name: str,
        inputs_json: str,
        outputs_json: str | None,
        status: str,
        duration_ms: int | None,
    ) -> None:
        await self._exec(
            "INSERT INTO tool_calls "
            "(id, run_id, step_id, tool_name, inputs_json, "
            " outputs_json, status, duration_ms, created_at) "
            "VALUES (:id, :run_id, :step_id, :tool_name, :inputs_json, "
            "        :outputs_json, :status, :duration_ms, :created_at) "
            "ON CONFLICT (id) DO NOTHING",
            {
                "id": call_id,
                "run_id": run_id,
                "step_id": step_id,
                "tool_name": tool_name,
                "inputs_json": inputs_json,
                "outputs_json": outputs_json,
                "status": status,
                "duration_ms": duration_ms,
                "created_at": _now(),
            },
        )


# --------------------------------------------------------------------------- #
# Factory                                                                      #
# --------------------------------------------------------------------------- #

def create_agent_db() -> AgentDB:
    """Return the correct AgentDB implementation for the current configuration."""
    if DB_ENGINE == "postgres":
        if not POSTGRES_URL:
            raise ValueError(
                "POSTGRES_URL must be set when DB_ENGINE=postgres. "
                "Example: postgresql://user:pass@localhost:5432/vloop"
            )
        return PostgresDB()
    return HarnessCoreDB()
