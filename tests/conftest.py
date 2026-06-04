"""Shared fixtures for route integration tests.

Creates a minimal FastAPI application with only the chat and views routers
mounted, backed by an in-memory SQLite database.  No MainProcess, no real
DSPy engine — AI calls are mocked via ``app.state.main_process``.
"""

from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from harness.data.db import Base, get_session
from harness.server.routes.analytics_routes import router as analytics_router
from harness.server.routes.chat_routes import router as chat_router
from harness.server.routes.views_routes import router as views_router

from harness.server.routes.dspy_routes import router as dspy_router
from harness.server.routes.settings_routes import router as settings_router
from harness.server.routes.pipeline_routes import router as pipeline_router
from harness.server.routes.optimization_routes import router as optimization_router
from harness.server.routes.vector_store_routes import router as vector_store_router




def _make_mock_main_process(ai_ready: bool = False) -> MagicMock:
    """Return a MagicMock that mimics MainProcess with an (un)ready AI engine."""
    mp = MagicMock()

    class MockAI:
        is_ready = ai_ready
        async def chat(self, *args, **kwargs):
            pred = MagicMock()
            pred.response = "Hello from AI!"
            pred.component_code = ""
            pred.pipeline_config = ""
            pred.view_stub_request = ""
            return pred
        async def generate_view(self, *args, **kwargs):
            pred = MagicMock()
            pred.react_code = "const App = () => <div>hello</div>;"
            pred.component_name = "TestComponent"
            pred.view_spec = "{}"
            return pred

    mp.ai = MockAI() if ai_ready else MagicMock(is_ready=False)

    # tools.catalog() returns an empty list by default
    mp.tools.catalog.return_value = []
    return mp



@pytest_asyncio.fixture
async def test_app(tmp_path: Path) -> AsyncIterator[FastAPI]:
    """Yield a FastAPI app wired to an in-memory DB and tmp VLoopStorage."""
    from harness.vloop.storage import VLoopStorage

    storage = VLoopStorage(cwd=tmp_path)

    # Build an in-memory SQLite engine and session factory
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    app = FastAPI()
    app.include_router(chat_router)
    app.include_router(views_router)
    app.include_router(analytics_router)

    app.include_router(dspy_router)
    app.include_router(settings_router)
    app.include_router(pipeline_router)
    app.include_router(optimization_router)
    app.include_router(vector_store_router)


    # Override the DB dependency so routes use our in-memory DB
    async def _override_get_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session
    app.state.vloop_storage = storage

    from harness.settings import HarnessSettings
    app.state.settings = HarnessSettings()

    # Provider Manager
    from harness.engine.providers import ProviderManager
    # mock vault and engine
    class MockVault:
        def get_key(self, k):
            return "sk-test"
    class MockEngine:
        pass

    pm = ProviderManager(engine=MockEngine(), vault=MockVault())
    app.state.provider_manager = pm

    app.state.main_process = _make_mock_main_process(ai_ready=False)

    # Mock for Vector Store
    from harness.engine.vector_store.store import InMemoryVecStore
    from harness.engine.vector_store.embeddings import LocalEmbeddings
    class MockEmbedder:
        async def embed(self, texts):
            return [[0.0] * 768 for _ in texts]
        def dimensions(self):
            return 768

    app.state.vector_store = InMemoryVecStore(dimensions=768)
    app.state.embedder = MockEmbedder()

    # Mock for pipeline builder
    from harness.engine.component_registry import DSPyComponentRegistry
    from harness.engine.pipeline_builder import PipelineBuilder
    registry = DSPyComponentRegistry()
    builder = PipelineBuilder(registry)
    app.state.component_registry = registry
    app.state.pipeline_builder = builder


    yield app

    await engine.dispose()


@pytest_asyncio.fixture
async def client(test_app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Yield an httpx AsyncClient pointed at the test FastAPI app."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
    ) as c:
        yield c
