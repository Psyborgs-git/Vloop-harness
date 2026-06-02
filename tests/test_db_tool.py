"""Tests for DatabaseTool — schema/query guards and timeout enforcement."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from harness.tools.db_tool import DatabaseTool


def _make_mp(workspace: Path) -> MagicMock:
    mp = MagicMock()
    mp.workspace_root = workspace
    registry = MagicMock()
    mp.tools = registry
    mp.permissions.has.return_value = True
    return mp


@pytest.mark.asyncio
async def test_query_read_requires_dict_params(tmp_path: Path) -> None:
    tool = DatabaseTool(_make_mp(tmp_path))
    result = await tool.execute(None, None, {"operation": "query_read", "sql": "SELECT 1", "params": []})
    assert not result.success
    assert "must be an object" in (result.error or "")


@pytest.mark.asyncio
async def test_query_write_parameter_tokens_require_params(tmp_path: Path) -> None:
    tool = DatabaseTool(_make_mp(tmp_path))
    result = await tool.execute(
        None,
        None,
        {"operation": "query_write", "sql": "UPDATE x SET y=:value WHERE id=1", "_confirmation_token": "ok"},
    )
    assert not result.success
    assert "named parameters" in (result.error or "")


@pytest.mark.asyncio
async def test_query_read_success_with_bound_params(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)"))
        await conn.execute(text("INSERT INTO items(name) VALUES ('alpha'), ('beta')"))

    monkeypatch.setattr("harness.data.db.get_session_factory", lambda: factory)
    tool = DatabaseTool(_make_mp(tmp_path))
    result = await tool.execute(
        None, None, {"operation": "query_read", "sql": "SELECT name FROM items WHERE id=:id", "params": {"id": 1}}
    )
    assert result.success
    assert "alpha" in result.output

    await engine.dispose()
