"""Tests for new agent run, app manifest, and tool trace repository methods.

Uses an in-memory SQLite database.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from harness.data.db import Base
from harness.data.repository import Repository


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest_asyncio.fixture
async def repo(session: AsyncSession) -> Repository:
    return Repository(session)


# ── AgentRun ───────────────────────────────────────────────────────────────────


class TestAgentRun:
    async def test_create_and_get(self, repo: Repository) -> None:
        run = await repo.create_agent_run(goal="Build a sentiment component")
        assert run.id
        assert run.status == "pending"
        assert run.autonomy_mode == "suggest"

        fetched = await repo.get_agent_run(run.id)
        assert fetched is not None
        assert fetched.goal == "Build a sentiment component"

    async def test_list_runs(self, repo: Repository) -> None:
        await repo.create_agent_run(goal="Run A")
        await repo.create_agent_run(goal="Run B")
        runs = await repo.list_agent_runs()
        assert len(runs) >= 2

    async def test_update_status(self, repo: Repository) -> None:
        run = await repo.create_agent_run(goal="Test update")
        await repo.update_agent_run(run.id, status="running")
        updated = await repo.get_agent_run(run.id)
        assert updated is not None
        assert updated.status == "running"

    async def test_add_and_list_steps(self, repo: Repository) -> None:
        run = await repo.create_agent_run(goal="Test steps")
        step = await repo.add_run_step(
            run_id=run.id,
            step_type="plan",
            input_data={"goal": "Test"},
            output_data={"plan_json": "[]"},
            duration_ms=42,
        )
        assert step.id
        assert step.run_id == run.id
        assert step.step_type == "plan"
        assert step.duration_ms == 42

        full = await repo.get_agent_run(run.id)
        assert full is not None
        assert len(full.steps) == 1

    async def test_delete_cascades_steps(self, repo: Repository) -> None:
        run = await repo.create_agent_run(goal="Delete me")
        await repo.add_run_step(run_id=run.id, step_type="message")
        await repo.delete_agent_run(run.id)
        assert await repo.get_agent_run(run.id) is None

    async def test_autonomy_mode_stored(self, repo: Repository) -> None:
        run = await repo.create_agent_run(
            goal="Autonomous run", autonomy_mode="autonomous"
        )
        assert run.autonomy_mode == "autonomous"

    async def test_session_id_stored(self, repo: Repository) -> None:
        run = await repo.create_agent_run(goal="With session", session_id="sess-abc")
        assert run.session_id == "sess-abc"


# ── AppManifest ────────────────────────────────────────────────────────────────


class TestAppManifest:
    async def test_create_and_get(self, repo: Repository) -> None:
        m = await repo.create_app_manifest(
            name="My App",
            description="A test app",
            backend_type="pipeline",
            backend_id="pipe_123",
            react_views=["ViewA"],
        )
        assert m.id
        assert m.status == "draft"
        assert m.react_views == ["ViewA"]

        fetched = await repo.get_app_manifest(m.id)
        assert fetched is not None
        assert fetched.name == "My App"

    async def test_list_all(self, repo: Repository) -> None:
        await repo.create_app_manifest(name="App1")
        await repo.create_app_manifest(name="App2")
        manifests = await repo.list_app_manifests()
        assert len(manifests) >= 2

    async def test_list_by_status(self, repo: Repository) -> None:
        m = await repo.create_app_manifest(name="Active App")
        await repo.update_app_manifest(m.id, status="active")
        active = await repo.list_app_manifests(status="active")
        assert any(x.id == m.id for x in active)

    async def test_promote_status(self, repo: Repository) -> None:
        m = await repo.create_app_manifest(name="Promotable")
        await repo.update_app_manifest(m.id, status="validated")
        updated = await repo.get_app_manifest(m.id)
        assert updated is not None
        assert updated.status == "validated"

    async def test_delete(self, repo: Repository) -> None:
        m = await repo.create_app_manifest(name="Delete me")
        await repo.delete_app_manifest(m.id)
        assert await repo.get_app_manifest(m.id) is None

    async def test_react_views_list(self, repo: Repository) -> None:
        m = await repo.create_app_manifest(
            name="Multi-view", react_views=["ViewA", "ViewB"]
        )
        assert m.react_views == ["ViewA", "ViewB"]


# ── ToolTrace ──────────────────────────────────────────────────────────────────


class TestToolTrace:
    async def test_record_and_list(self, repo: Repository) -> None:
        trace = await repo.record_tool_trace(
            tool_name="terminal",
            inputs={"command": "echo hello"},
            outputs={"output": "hello"},
            risk_level="caution",
            duration_ms=10,
            success=True,
        )
        assert trace.id
        assert trace.tool_name == "terminal"

        traces = await repo.list_tool_traces()
        assert any(t.id == trace.id for t in traces)

    async def test_filter_by_tool_name(self, repo: Repository) -> None:
        await repo.record_tool_trace(tool_name="filesystem", success=True)
        await repo.record_tool_trace(tool_name="terminal", success=True)
        fs_traces = await repo.list_tool_traces(tool_name="filesystem")
        assert all(t.tool_name == "filesystem" for t in fs_traces)

    async def test_filter_by_session(self, repo: Repository) -> None:
        await repo.record_tool_trace(
            tool_name="browser", session_id="sess-xyz", success=True
        )
        traces = await repo.list_tool_traces(session_id="sess-xyz")
        assert all(t.session_id == "sess-xyz" for t in traces)

    async def test_success_flag(self, repo: Repository) -> None:
        trace = await repo.record_tool_trace(tool_name="database", success=False)
        assert not trace.success

    async def test_limit(self, repo: Repository) -> None:
        for i in range(5):
            await repo.record_tool_trace(tool_name=f"tool_{i}", success=True)
        traces = await repo.list_tool_traces(limit=3)
        assert len(traces) <= 3
