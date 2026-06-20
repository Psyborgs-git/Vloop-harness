"""SQLite-backed persistence for control-plane provider, agent, and invocation state."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterable


class SQLiteState:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def fetch_all(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(sql, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    def fetch_one(self, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(sql, tuple(params)).fetchone()
        return dict(row) if row is not None else None

    def execute(self, sql: str, params: Iterable[Any] = ()) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(sql, tuple(params))
            connection.commit()

    def executemany(self, sql: str, params: Iterable[Iterable[Any]]) -> None:
        with self._lock, self._connect() as connection:
            connection.executemany(sql, [tuple(row) for row in params])
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS providers (
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
                );

                CREATE TABLE IF NOT EXISTS agents (
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
                );

                CREATE TABLE IF NOT EXISTS invocations (
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
                );

                CREATE TABLE IF NOT EXISTS invocation_events (
                    invocation_id TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (invocation_id, seq)
                );
                """
            )
            connection.commit()


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def from_json(value: str | None, default: Any) -> Any:
    if not value:
        return default
    return json.loads(value)
