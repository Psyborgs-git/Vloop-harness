"""Pluggable database backends for the VLoop control plane.

Supports SQLite (default/fallback), PostgreSQL, and DuckDB.
All backends expose the same synchronous interface used by
ProviderService and AgentOrchestrator.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from abc import ABC, abstractmethod
from contextlib import closing
from pathlib import Path
from typing import Any, Iterable

LOGGER = logging.getLogger("vloop.control_plane.database")

# ---------------------------------------------------------------------------
# Schema shared across backends
# ---------------------------------------------------------------------------

_SCHEMA_STATEMENTS = [
    # providers
    """CREATE TABLE IF NOT EXISTS providers (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        provider_type TEXT NOT NULL,
        enabled INTEGER NOT NULL,
        default_model TEXT,
        api_base TEXT,
        api_version TEXT,
        organization TEXT,
        secret_mode TEXT NOT NULL,
        secret_env_var TEXT,
        revision INTEGER NOT NULL,
        last_test_status TEXT NOT NULL,
        last_test_error TEXT,
        last_tested_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    # agents
    """CREATE TABLE IF NOT EXISTS agents (
        id TEXT PRIMARY KEY,
        slug TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        description TEXT,
        enabled INTEGER NOT NULL,
        instructions TEXT NOT NULL,
        reasoning_mode TEXT NOT NULL,
        input_fields_json TEXT NOT NULL,
        output_mode TEXT NOT NULL,
        output_field_name TEXT NOT NULL,
        output_schema_json TEXT,
        default_provider_id TEXT NOT NULL,
        model_override TEXT,
        temperature REAL NOT NULL,
        max_tokens INTEGER NOT NULL,
        revision INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    # invocations
    """CREATE TABLE IF NOT EXISTS invocations (
        id TEXT PRIMARY KEY,
        agent_id TEXT NOT NULL,
        agent_revision INTEGER NOT NULL,
        provider_id TEXT NOT NULL,
        provider_revision INTEGER NOT NULL,
        status TEXT NOT NULL,
        inputs_json TEXT NOT NULL,
        overrides_json TEXT NOT NULL,
        resolved_model TEXT NOT NULL,
        resolved_config_json TEXT NOT NULL,
        output_text TEXT,
        output_json TEXT,
        reasoning_text TEXT,
        usage_json TEXT,
        error_code TEXT,
        error_message TEXT,
        created_at TEXT NOT NULL,
        started_at TEXT,
        finished_at TEXT
    )""",
    # invocation_events
    """CREATE TABLE IF NOT EXISTS invocation_events (
        invocation_id TEXT NOT NULL,
        seq INTEGER NOT NULL,
        type TEXT NOT NULL,
        message TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        elapsed_ms INTEGER,
        created_at TEXT NOT NULL,
        PRIMARY KEY (invocation_id, seq)
    )""",
    # usage_logs
    """CREATE TABLE IF NOT EXISTS usage_logs (
        invocation_id TEXT NOT NULL,
        phase TEXT NOT NULL,
        prompt_tokens INTEGER NOT NULL DEFAULT 0,
        completion_tokens INTEGER NOT NULL DEFAULT 0,
        total_tokens INTEGER NOT NULL DEFAULT 0,
        model TEXT,
        created_at TEXT NOT NULL,
        PRIMARY KEY (invocation_id, phase)
    )""",
    # ------------------------------------------------------------------
    # Orchestration engine tables
    # ------------------------------------------------------------------
    # workflow_definitions
    """CREATE TABLE IF NOT EXISTS workflow_definitions (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        objective TEXT,
        definition_json TEXT NOT NULL,
        revision INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    # workflow_runs
    """CREATE TABLE IF NOT EXISTS workflow_runs (
        id TEXT PRIMARY KEY,
        definition_id TEXT NOT NULL,
        state TEXT NOT NULL,
        concurrency_limit INTEGER NOT NULL,
        budget_json TEXT,
        created_at TEXT NOT NULL,
        started_at TEXT,
        finished_at TEXT
    )""",
    # workflow_steps
    """CREATE TABLE IF NOT EXISTS workflow_steps (
        run_id TEXT NOT NULL,
        step_id TEXT NOT NULL,
        step_type TEXT NOT NULL,
        state TEXT NOT NULL,
        depends_on_json TEXT NOT NULL,
        inputs_json TEXT,
        output_json TEXT,
        error_message TEXT,
        started_at TEXT,
        finished_at TEXT,
        PRIMARY KEY (run_id, step_id)
    )""",
    # workflow_events
    """CREATE TABLE IF NOT EXISTS workflow_events (
        run_id TEXT NOT NULL,
        seq INTEGER NOT NULL,
        type TEXT NOT NULL,
        step_id TEXT,
        message TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (run_id, seq)
    )""",
    # scheduled_tasks
    """CREATE TABLE IF NOT EXISTS scheduled_tasks (
        id TEXT PRIMARY KEY,
        definition_id TEXT NOT NULL,
        cron_expression TEXT NOT NULL,
        state TEXT NOT NULL,
        next_run_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    # memory_entries
    """CREATE TABLE IF NOT EXISTS memory_entries (
        id TEXT PRIMARY KEY,
        category TEXT NOT NULL,
        content TEXT NOT NULL,
        size_bytes INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    # checkpoints
    """CREATE TABLE IF NOT EXISTS checkpoints (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        workspace_id TEXT NOT NULL,
        kernel_snapshot_ref TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    # toolsets
    """CREATE TABLE IF NOT EXISTS toolsets (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        tools_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    # mcp_servers
    """CREATE TABLE IF NOT EXISTS mcp_servers (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        transport TEXT NOT NULL,
        tool_filter_json TEXT,
        grant_ref TEXT,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
]


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------


class DatabaseBackend(ABC):
    """Synchronous database interface used by all CP services."""

    @abstractmethod
    def fetch_all(
        self, sql: str, params: Iterable[Any] = ()
    ) -> list[dict[str, Any]]: ...

    @abstractmethod
    def fetch_one(
        self, sql: str, params: Iterable[Any] = ()
    ) -> dict[str, Any] | None: ...

    @abstractmethod
    def execute(self, sql: str, params: Iterable[Any] = ()) -> None: ...

    @abstractmethod
    def executemany(self, sql: str, params: Iterable[Iterable[Any]]) -> None: ...

    @abstractmethod
    def initialize(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...


# ---------------------------------------------------------------------------
# SQLite backend (default / fallback)
# ---------------------------------------------------------------------------


class SQLiteBackend(DatabaseBackend):
    """SQLite backend with WAL mode and thread-safe access."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db_module()
        self.initialize()

    def _init_db_module(self) -> None:
        import sqlite3

        self._sqlite3 = sqlite3

    def fetch_all(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        with self._lock, closing(self._connect()) as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    def fetch_one(self, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        with self._lock, closing(self._connect()) as conn:
            row = conn.execute(sql, tuple(params)).fetchone()
        return dict(row) if row is not None else None

    def execute(self, sql: str, params: Iterable[Any] = ()) -> None:
        with self._lock, closing(self._connect()) as conn:
            conn.execute(sql, tuple(params))
            conn.commit()

    def executemany(self, sql: str, params: Iterable[Iterable[Any]]) -> None:
        with self._lock, closing(self._connect()) as conn:
            conn.executemany(sql, [tuple(row) for row in params])
            conn.commit()

    def _connect(self):
        conn = self._sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = self._sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self._lock, closing(self._connect()) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            for statement in _SCHEMA_STATEMENTS:
                conn.execute(statement)
            conn.commit()

    def close(self) -> None:
        pass  # SQLite connection is per-operation


# ---------------------------------------------------------------------------
# PostgreSQL backend
# ---------------------------------------------------------------------------


class PostgresBackend(DatabaseBackend):
    """PostgreSQL backend via psycopg2.  Converts ? → %s placeholders automatically."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self._init_db_module()
        self._lock = threading.RLock()
        self.initialize()

    def _init_db_module(self) -> None:
        try:
            import psycopg2
            import psycopg2.extras

            self._psycopg2 = psycopg2
            self._extras = psycopg2.extras
        except ImportError as exc:
            raise RuntimeError(
                "psycopg2 / psycopg2-binary is required for PostgreSQL support. "
                "Install it with: pip install psycopg2-binary"
            ) from exc

    def _get_conn(self):
        try:
            conn = self._psycopg2.connect(self.database_url)
            conn.autocommit = False
            return conn
        except Exception:
            LOGGER.exception(
                "Failed to connect to PostgreSQL at %s", _redact_url(self.database_url)
            )
            raise

    @staticmethod
    def _adapt_sql(sql: str) -> str:
        """Convert SQLite ? placeholders to PostgreSQL %s."""
        return sql.replace("?", "%s")

    def fetch_all(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        with self._lock:
            conn = self._get_conn()
            try:
                with conn.cursor(cursor_factory=self._extras.RealDictCursor) as cur:
                    cur.execute(self._adapt_sql(sql), tuple(params))
                    rows = cur.fetchall()
                return [dict(row) for row in rows]
            finally:
                conn.close()

    def fetch_one(self, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        with self._lock:
            conn = self._get_conn()
            try:
                with conn.cursor(cursor_factory=self._extras.RealDictCursor) as cur:
                    cur.execute(self._adapt_sql(sql), tuple(params))
                    row = cur.fetchone()
                return dict(row) if row is not None else None
            finally:
                conn.close()

    def execute(self, sql: str, params: Iterable[Any] = ()) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute(self._adapt_sql(sql), tuple(params))
                conn.commit()
            finally:
                conn.close()

    def executemany(self, sql: str, params: Iterable[Iterable[Any]]) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                with conn.cursor() as cur:
                    cur.executemany(
                        self._adapt_sql(sql), [tuple(row) for row in params]
                    )
                conn.commit()
            finally:
                conn.close()

    def initialize(self) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                with conn.cursor() as cur:
                    for statement in _SCHEMA_STATEMENTS:
                        cur.execute(statement)
                conn.commit()
            finally:
                conn.close()

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# DuckDB backend
# ---------------------------------------------------------------------------


class DuckDBBackend(DatabaseBackend):
    """DuckDB backend — file-based, OLAP-friendly, great for analytics.

    Paths can be ``:memory:``, a file path, or ``md:``/``s3:`` URLs.
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_db_module()
        self._lock = threading.RLock()
        self._initialize_connection()
        self.initialize()

    def _init_db_module(self) -> None:
        try:
            import duckdb

            self._duckdb = duckdb
        except ImportError as exc:
            raise RuntimeError(
                "duckdb is required for DuckDB support. "
                "Install it with: pip install duckdb"
            ) from exc

    def _initialize_connection(self) -> None:
        self._conn = self._duckdb.connect(self.db_path)

    def fetch_all(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        with self._lock:
            result = self._conn.execute(sql, tuple(params))
            columns = [desc[0] for desc in result.description]
            return [dict(zip(columns, row)) for row in result.fetchall()]

    def fetch_one(self, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        with self._lock:
            result = self._conn.execute(sql, tuple(params))
            columns = [desc[0] for desc in result.description]
            row = result.fetchone()
            return dict(zip(columns, row)) if row is not None else None

    def execute(self, sql: str, params: Iterable[Any] = ()) -> None:
        with self._lock:
            self._conn.execute(sql, tuple(params))

    def executemany(self, sql: str, params: Iterable[Iterable[Any]]) -> None:
        with self._lock:
            self._conn.executemany(sql, [tuple(row) for row in params])

    def initialize(self) -> None:
        with self._lock:
            for statement in _SCHEMA_STATEMENTS:
                self._conn.execute(statement)

    def close(self) -> None:
        with self._lock:
            self._conn.close()


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_database(
    database_url: str | None = None,
    runtime_root: Path | None = None,
) -> DatabaseBackend:
    """Create the appropriate database backend from a connection URL.

    Resolution order:
    1. Explicit ``database_url`` argument
    2. ``VLOOP_DATABASE_URL`` environment variable
    3. Fallback: SQLite at ``<runtime_root>/data/control-plane.db``

    URL schemes:
    - ``sqlite:///path/to/db`` or no scheme  → SQLiteBackend
    - ``postgresql://...`` or ``postgres://`` → PostgresBackend
    - ``duckdb://path`` or ``duckdb:path``    → DuckDBBackend
    """
    db_url = (database_url or os.environ.get("VLOOP_DATABASE_URL", "") or "").strip()

    if runtime_root is None:
        runtime_root = Path(
            os.environ.get("VLOOP_RUNTIME_ROOT", Path.home() / ".vloop")
        )

    if db_url.startswith("postgresql://") or db_url.startswith("postgres://"):
        LOGGER.info("Using PostgreSQL backend: %s", _redact_url(db_url))
        return PostgresBackend(db_url)

    if db_url.startswith("duckdb://"):
        path = db_url[len("duckdb://") :]
        if not path:
            path = str(runtime_root / "data" / "control-plane.duckdb")
        LOGGER.info("Using DuckDB backend: %s", path)
        return DuckDBBackend(path)

    if db_url.startswith("duckdb:"):
        path = db_url[len("duckdb:") :]
        if not path:
            path = str(runtime_root / "data" / "control-plane.duckdb")
        LOGGER.info("Using DuckDB backend: %s", path)
        return DuckDBBackend(path)

    if db_url.startswith("sqlite://"):
        path = db_url[len("sqlite://") :]
        LOGGER.info("Using SQLite backend (from URL): %s", path)
        return SQLiteBackend(Path(path))

    # Fallback
    sqlite_path = runtime_root / "data" / "control-plane.db"
    LOGGER.info("Using SQLite backend (fallback): %s", sqlite_path)
    return SQLiteBackend(sqlite_path)


def _redact_url(url: str) -> str:
    """Strip password from a connection URL for safe logging."""
    return re.sub(r":([^@]+)@", ":****@", url)
