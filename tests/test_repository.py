"""Async unit tests for harness.data.repository.Repository.

Uses an in-memory SQLite database so no files are left on disk.

Covers:
  - ChatSession CRUD (create, list, get, rename, delete)
  - ChatMessage CRUD (add, list, cascade delete)
  - GeneratedView CRUD (save, list, get, delete)
  - DSPyComponentDef basic save/list
  - PipelineDef basic save/list
  - ProviderConfigDB save/list/set-default/delete
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from harness.data.db import Base
from harness.data.models import (
    DSPyComponentDef,
    GeneratedView,
    PipelineDef,
    ProviderConfigDB,
)
from harness.data.repository import Repository


# ── Shared async session fixture ───────────────────────────────────────────────


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


# ── ChatSession ────────────────────────────────────────────────────────────────


class TestChatSession:
    async def test_create_session_default_title(self, repo: Repository) -> None:
        s = await repo.create_session()
        assert s.title == "New Chat"
        assert s.id

    async def test_create_session_custom_title(self, repo: Repository) -> None:
        s = await repo.create_session(title="My Thread")
        assert s.title == "My Thread"

    async def test_list_sessions_empty(self, repo: Repository) -> None:
        result = await repo.list_sessions()
        assert result == []

    async def test_list_sessions_returns_all(self, repo: Repository) -> None:
        await repo.create_session("A")
        await repo.create_session("B")
        sessions = await repo.list_sessions()
        assert len(sessions) == 2

    async def test_get_session_exists(self, repo: Repository) -> None:
        s = await repo.create_session("Found")
        fetched = await repo.get_session(s.id)
        assert fetched is not None
        assert fetched.title == "Found"

    async def test_get_session_missing_returns_none(self, repo: Repository) -> None:
        result = await repo.get_session("nonexistent-id")
        assert result is None

    async def test_rename_session(self, repo: Repository) -> None:
        s = await repo.create_session("Old")
        await repo.update_session_title(s.id, "New")
        fetched = await repo.get_session(s.id)
        assert fetched is not None
        assert fetched.title == "New"

    async def test_delete_session(self, repo: Repository) -> None:
        s = await repo.create_session("ToDelete")
        await repo.delete_session(s.id)
        assert await repo.get_session(s.id) is None

    async def test_delete_nonexistent_session_is_safe(self, repo: Repository) -> None:
        # Must not raise
        await repo.delete_session("ghost-id")


# ── ChatMessage ────────────────────────────────────────────────────────────────


class TestChatMessage:
    async def test_add_message_returns_persisted_record(self, repo: Repository) -> None:
        s = await repo.create_session()
        m = await repo.add_message(s.id, "user", "hello")
        assert m.id
        assert m.role == "user"
        assert m.content == "hello"

    async def test_add_message_with_meta(self, repo: Repository) -> None:
        s = await repo.create_session()
        m = await repo.add_message(s.id, "assistant", "code here", meta={"saved_component_id": "c1"})
        assert m.meta["saved_component_id"] == "c1"

    async def test_get_messages_ordered_by_created_at(self, repo: Repository) -> None:
        s = await repo.create_session()
        for i in range(5):
            await repo.add_message(s.id, "user", f"msg {i}")
        msgs = await repo.get_messages(s.id)
        assert len(msgs) == 5
        contents = [m.content for m in msgs]
        assert contents == [f"msg {i}" for i in range(5)]

    async def test_get_messages_empty_for_new_session(self, repo: Repository) -> None:
        s = await repo.create_session()
        assert await repo.get_messages(s.id) == []

    async def test_delete_session_cascades_messages(self, repo: Repository) -> None:
        s = await repo.create_session()
        await repo.add_message(s.id, "user", "hello")
        await repo.add_message(s.id, "assistant", "world")
        await repo.delete_session(s.id)
        # After cascade, messages should be gone
        msgs = await repo.get_messages(s.id)
        assert msgs == []

    async def test_session_messages_loaded_via_get_session(self, repo: Repository) -> None:
        s = await repo.create_session()
        await repo.add_message(s.id, "user", "hi")
        fetched = await repo.get_session(s.id)
        assert fetched is not None
        assert len(fetched.messages) == 1


# ── GeneratedView ──────────────────────────────────────────────────────────────


class TestGeneratedView:
    def _make_view(self, **kwargs) -> GeneratedView:
        defaults = dict(
            name="Test view",
            component_name="TestView",
            react_code="export default function TestView() { return null; }",
            view_spec="A test view",
            file_path=None,
            session_id=None,
        )
        defaults.update(kwargs)
        return GeneratedView(**defaults)

    async def test_save_view_persists(self, repo: Repository) -> None:
        view = self._make_view()
        saved = await repo.save_view(view)
        assert saved.id
        assert saved.component_name == "TestView"

    async def test_list_views_empty(self, repo: Repository) -> None:
        assert await repo.list_views() == []

    async def test_list_views_returns_all(self, repo: Repository) -> None:
        await repo.save_view(self._make_view(component_name="ViewA"))
        await repo.save_view(self._make_view(component_name="ViewB"))
        views = await repo.list_views()
        assert len(views) == 2

    async def test_get_view_by_id(self, repo: Repository) -> None:
        saved = await repo.save_view(self._make_view(component_name="FetchMe"))
        fetched = await repo.get_view(saved.id)
        assert fetched is not None
        assert fetched.component_name == "FetchMe"

    async def test_get_view_missing_returns_none(self, repo: Repository) -> None:
        assert await repo.get_view("no-such-id") is None

    async def test_delete_view_removes_record(self, repo: Repository) -> None:
        saved = await repo.save_view(self._make_view())
        await repo.delete_view(saved.id)
        assert await repo.get_view(saved.id) is None

    async def test_delete_view_nonexistent_is_safe(self, repo: Repository) -> None:
        await repo.delete_view("ghost")

    async def test_view_with_session_id(self, repo: Repository) -> None:
        s = await repo.create_session()
        view = self._make_view(session_id=s.id)
        saved = await repo.save_view(view)
        assert saved.session_id == s.id

    async def test_list_views_ordered_newest_first(self, repo: Repository) -> None:
        v1 = await repo.save_view(self._make_view(component_name="First"))
        v2 = await repo.save_view(self._make_view(component_name="Second"))
        views = await repo.list_views()
        # Most recently created is returned first
        names = [v.component_name for v in views]
        assert names[0] == "Second"
        assert names[1] == "First"


# ── DSPyComponentDef ───────────────────────────────────────────────────────────


class TestDSPyComponentDef:
    def _make_comp(self, comp_id: str = "c1") -> DSPyComponentDef:
        return DSPyComponentDef(
            id=comp_id,
            name="TestComp",
            description="A test component",
            code="class TestSig(dspy.Signature): pass",
            module_type="ChainOfThought",
            signature_fields={"inputs": [], "outputs": []},
        )

    async def test_save_component(self, repo: Repository) -> None:
        comp = await repo.save_component(self._make_comp("c1"))
        assert comp.id == "c1"

    async def test_list_components_empty(self, repo: Repository) -> None:
        assert await repo.list_components() == []

    async def test_list_components_returns_saved(self, repo: Repository) -> None:
        await repo.save_component(self._make_comp("c1"))
        await repo.save_component(self._make_comp("c2"))
        comps = await repo.list_components()
        assert len(comps) == 2

    async def test_update_component_if_exists(self, repo: Repository) -> None:
        comp = self._make_comp("c1")
        await repo.save_component(comp)
        comp.name = "Updated"
        await repo.save_component(comp)
        fetched = await repo.get_component("c1")
        assert fetched is not None
        assert fetched.name == "Updated"

    async def test_delete_component(self, repo: Repository) -> None:
        await repo.save_component(self._make_comp("del1"))
        await repo.delete_component("del1")
        assert await repo.get_component("del1") is None


# ── PipelineDef ────────────────────────────────────────────────────────────────


class TestPipelineDef:
    def _make_pipe(self, pipe_id: str = "p1") -> PipelineDef:
        return PipelineDef(
            id=pipe_id,
            name="TestPipe",
            description="desc",
            steps=[{"type": "component", "component_id": "c1"}],
        )

    async def test_save_pipeline(self, repo: Repository) -> None:
        pipe = await repo.save_pipeline(self._make_pipe())
        assert pipe.id == "p1"

    async def test_list_pipelines_empty(self, repo: Repository) -> None:
        assert await repo.list_pipelines() == []

    async def test_get_pipeline(self, repo: Repository) -> None:
        await repo.save_pipeline(self._make_pipe("p99"))
        p = await repo.get_pipeline("p99")
        assert p is not None
        assert p.name == "TestPipe"

    async def test_delete_pipeline(self, repo: Repository) -> None:
        await repo.save_pipeline(self._make_pipe("del_p"))
        await repo.delete_pipeline("del_p")
        assert await repo.get_pipeline("del_p") is None


# ── ProviderConfigDB ───────────────────────────────────────────────────────────


class TestProviderConfigDB:
    def _make_provider(self, provider_id: str = "prov1") -> ProviderConfigDB:
        return ProviderConfigDB(
            id=provider_id,
            name="Ollama Local",
            provider_type="ollama",
            model="llama3",
            base_url="http://localhost:11434",
        )

    async def test_save_provider(self, repo: Repository) -> None:
        p = await repo.save_provider(self._make_provider())
        assert p.id == "prov1"

    async def test_list_providers_empty(self, repo: Repository) -> None:
        assert await repo.list_providers() == []

    async def test_list_providers_returns_all(self, repo: Repository) -> None:
        await repo.save_provider(self._make_provider("p1"))
        await repo.save_provider(self._make_provider("p2"))
        assert len(await repo.list_providers()) == 2

    async def test_get_provider(self, repo: Repository) -> None:
        await repo.save_provider(self._make_provider("get_me"))
        p = await repo.get_provider("get_me")
        assert p is not None
        assert p.name == "Ollama Local"

    async def test_set_default_provider(self, repo: Repository) -> None:
        p1 = self._make_provider("def1")
        p2 = self._make_provider("def2")
        await repo.save_provider(p1)
        await repo.save_provider(p2)
        await repo.set_default_provider("def1")
        d = await repo.get_default_provider()
        assert d is not None
        assert d.id == "def1"

    async def test_set_default_clears_previous(self, repo: Repository) -> None:
        await repo.save_provider(self._make_provider("a"))
        await repo.save_provider(self._make_provider("b"))
        await repo.set_default_provider("a")
        await repo.set_default_provider("b")
        d = await repo.get_default_provider()
        assert d is not None
        assert d.id == "b"

    async def test_delete_provider(self, repo: Repository) -> None:
        await repo.save_provider(self._make_provider("to_del"))
        await repo.delete_provider("to_del")
        assert await repo.get_provider("to_del") is None

    async def test_get_default_provider_none_if_unset(self, repo: Repository) -> None:
        await repo.save_provider(self._make_provider())
        assert await repo.get_default_provider() is None
