"""Unit tests for orchestration-engine schema creation and persistence round-trip.

Covers task 1.2: verify each of the nine orchestration tables added in task 1.1
is created on the SQLite backend and that a representative row inserts and reads
back unchanged via the ``DatabaseBackend`` interface (including JSON columns
serialized with ``core.helpers.to_json``/``from_json``).

_Requirements: 3.7, 14.1_
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.database import SQLiteBackend
from core.helpers import from_json, now_iso, to_json

# The nine orchestration tables introduced in task 1.1.
ORCHESTRATION_TABLES = [
    "workflow_definitions",
    "workflow_runs",
    "workflow_steps",
    "workflow_events",
    "scheduled_tasks",
    "memory_entries",
    "checkpoints",
    "toolsets",
    "mcp_servers",
]


@pytest.fixture()
def backend(tmp_path: Path) -> SQLiteBackend:
    """A fresh, initialized SQLite backend backed by a temp file."""
    return SQLiteBackend(tmp_path / "schema-test.db")


# ---------------------------------------------------------------------------
# Schema creation
# ---------------------------------------------------------------------------


def _existing_tables(backend: SQLiteBackend) -> set[str]:
    rows = backend.fetch_all(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    )
    return {row["name"] for row in rows}


def test_initialize_creates_all_orchestration_tables(backend: SQLiteBackend):
    tables = _existing_tables(backend)
    for name in ORCHESTRATION_TABLES:
        assert name in tables, f"missing orchestration table: {name}"


@pytest.mark.parametrize("table", ORCHESTRATION_TABLES)
def test_each_table_is_queryable(backend: SQLiteBackend, table: str):
    # A freshly created table must exist and be empty (queryable without error).
    rows = backend.fetch_all(f"SELECT * FROM {table}")  # noqa: S608 - fixed names
    assert rows == []


# ---------------------------------------------------------------------------
# Persistence round-trip per table
# ---------------------------------------------------------------------------


def test_workflow_definitions_round_trip(backend: SQLiteBackend):
    ts = now_iso()
    definition = {
        "version": 1,
        "name": "Build report",
        "objective": "compile",
        "inputs": {"a": 1},
        "steps": [{"id": "s1", "type": "agent", "config": {}, "dependsOn": []}],
        "policies": {"max_retries": 2},
    }
    backend.execute(
        "INSERT INTO workflow_definitions "
        "(id, name, objective, definition_json, revision, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("def-1", "Build report", "compile", to_json(definition), 1, ts, ts),
    )

    row = backend.fetch_one(
        "SELECT * FROM workflow_definitions WHERE id = ?", ("def-1",)
    )
    assert row is not None
    assert row["name"] == "Build report"
    assert row["objective"] == "compile"
    assert row["revision"] == 1
    assert row["created_at"] == ts
    assert from_json(row["definition_json"], None) == definition


def test_workflow_runs_round_trip(backend: SQLiteBackend):
    ts = now_iso()
    budget = {"max_tokens": 1000, "used_tokens": 0, "used_cost": 0.0}
    backend.execute(
        "INSERT INTO workflow_runs "
        "(id, definition_id, state, concurrency_limit, budget_json, "
        "created_at, started_at, finished_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("run-1", "def-1", "pending", 4, to_json(budget), ts, None, None),
    )

    row = backend.fetch_one("SELECT * FROM workflow_runs WHERE id = ?", ("run-1",))
    assert row is not None
    assert row["definition_id"] == "def-1"
    assert row["state"] == "pending"
    assert row["concurrency_limit"] == 4
    assert row["started_at"] is None
    assert row["finished_at"] is None
    assert from_json(row["budget_json"], None) == budget


def test_workflow_steps_round_trip(backend: SQLiteBackend):
    ts = now_iso()
    depends_on = ["s0", "s1"]
    inputs = {"prompt": "hi"}
    output = {"value": 42}
    backend.execute(
        "INSERT INTO workflow_steps "
        "(run_id, step_id, step_type, state, depends_on_json, inputs_json, "
        "output_json, error_message, started_at, finished_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "run-1",
            "s2",
            "agent",
            "completed",
            to_json(depends_on),
            to_json(inputs),
            to_json(output),
            None,
            ts,
            ts,
        ),
    )

    row = backend.fetch_one(
        "SELECT * FROM workflow_steps WHERE run_id = ? AND step_id = ?",
        ("run-1", "s2"),
    )
    assert row is not None
    assert row["step_type"] == "agent"
    assert row["state"] == "completed"
    assert row["error_message"] is None
    assert from_json(row["depends_on_json"], None) == depends_on
    assert from_json(row["inputs_json"], None) == inputs
    assert from_json(row["output_json"], None) == output


def test_workflow_steps_composite_primary_key(backend: SQLiteBackend):
    ts = now_iso()
    args = ("run-1", "s1", "agent", "pending", to_json([]), None, None, None, ts, ts)
    sql = (
        "INSERT INTO workflow_steps "
        "(run_id, step_id, step_type, state, depends_on_json, inputs_json, "
        "output_json, error_message, started_at, finished_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
    backend.execute(sql, args)
    # The same (run_id, step_id) pair violates the composite primary key.
    with pytest.raises(Exception):
        backend.execute(sql, args)


def test_workflow_events_round_trip(backend: SQLiteBackend):
    ts = now_iso()
    payload = {"detail": "step started", "step": "s1"}
    backend.execute(
        "INSERT INTO workflow_events "
        "(run_id, seq, type, step_id, message, payload_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("run-1", 1, "step.state_changed", "s1", "started", to_json(payload), ts),
    )

    row = backend.fetch_one(
        "SELECT * FROM workflow_events WHERE run_id = ? AND seq = ?", ("run-1", 1)
    )
    assert row is not None
    assert row["type"] == "step.state_changed"
    assert row["step_id"] == "s1"
    assert row["message"] == "started"
    assert from_json(row["payload_json"], None) == payload


def test_scheduled_tasks_round_trip(backend: SQLiteBackend):
    ts = now_iso()
    backend.execute(
        "INSERT INTO scheduled_tasks "
        "(id, definition_id, cron_expression, state, next_run_at, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("task-1", "def-1", "0 9 * * *", "active", ts, ts, ts),
    )

    row = backend.fetch_one(
        "SELECT * FROM scheduled_tasks WHERE id = ?", ("task-1",)
    )
    assert row is not None
    assert row["definition_id"] == "def-1"
    assert row["cron_expression"] == "0 9 * * *"
    assert row["state"] == "active"
    assert row["next_run_at"] == ts


def test_memory_entries_round_trip(backend: SQLiteBackend):
    ts = now_iso()
    content = "User prefers concise answers."
    backend.execute(
        "INSERT INTO memory_entries "
        "(id, category, content, size_bytes, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("mem-1", "preference", content, len(content.encode()), ts, ts),
    )

    row = backend.fetch_one("SELECT * FROM memory_entries WHERE id = ?", ("mem-1",))
    assert row is not None
    assert row["category"] == "preference"
    assert row["content"] == content
    assert row["size_bytes"] == len(content.encode())


def test_checkpoints_round_trip(backend: SQLiteBackend):
    ts = now_iso()
    backend.execute(
        "INSERT INTO checkpoints "
        "(id, run_id, workspace_id, kernel_snapshot_ref, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("cp-1", "run-1", "ws-1", "snap-ref-abc", ts),
    )

    row = backend.fetch_one("SELECT * FROM checkpoints WHERE id = ?", ("cp-1",))
    assert row is not None
    assert row["run_id"] == "run-1"
    assert row["workspace_id"] == "ws-1"
    # Control_Plane stores only a kernel snapshot reference, never contents.
    assert row["kernel_snapshot_ref"] == "snap-ref-abc"


def test_toolsets_round_trip(backend: SQLiteBackend):
    ts = now_iso()
    tools = ["web_search", "file_read"]
    backend.execute(
        "INSERT INTO toolsets (id, name, tools_json, created_at) "
        "VALUES (?, ?, ?, ?)",
        ("ts-1", "research", to_json(tools), ts),
    )

    row = backend.fetch_one("SELECT * FROM toolsets WHERE id = ?", ("ts-1",))
    assert row is not None
    assert row["name"] == "research"
    assert from_json(row["tools_json"], None) == tools


def test_mcp_servers_round_trip(backend: SQLiteBackend):
    ts = now_iso()
    tool_filter = ["search", "fetch"]
    backend.execute(
        "INSERT INTO mcp_servers "
        "(id, name, transport, tool_filter_json, grant_ref, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("mcp-1", "docs", "stdio", to_json(tool_filter), "grant-1", "connected", ts),
    )

    row = backend.fetch_one("SELECT * FROM mcp_servers WHERE id = ?", ("mcp-1",))
    assert row is not None
    assert row["name"] == "docs"
    assert row["transport"] == "stdio"
    # grant_ref is a reference only, never a raw secret value.
    assert row["grant_ref"] == "grant-1"
    assert row["status"] == "connected"
    assert from_json(row["tool_filter_json"], None) == tool_filter


def test_round_trip_persists_across_new_backend_instance(tmp_path: Path):
    """A row written by one backend instance is readable by a new instance
    pointed at the same file — schema and data survive a restart (Req 3.7)."""
    db_path = tmp_path / "persist.db"
    ts = now_iso()

    writer = SQLiteBackend(db_path)
    writer.execute(
        "INSERT INTO workflow_runs "
        "(id, definition_id, state, concurrency_limit, budget_json, "
        "created_at, started_at, finished_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("run-persist", "def-1", "awaiting_approval", 2, None, ts, ts, None),
    )

    # Re-open the same database file as a brand-new backend (simulated restart).
    reader = SQLiteBackend(db_path)
    row = reader.fetch_one(
        "SELECT * FROM workflow_runs WHERE id = ?", ("run-persist",)
    )
    assert row is not None
    assert row["state"] == "awaiting_approval"
    assert row["concurrency_limit"] == 2
