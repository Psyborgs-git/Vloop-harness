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
from harness.server.routes.chat_routes import router as chat_router
from harness.server.routes.views_routes import router as views_router


def _make_mock_main_process(ai_ready: bool = False) -> MagicMock:
    """Return a MagicMock that mimics MainProcess with an (un)ready AI engine."""
    mp = MagicMock()
    mp.ai.is_ready = ai_ready
    # tools.catalog() returns an empty list by default
    mp.tools.catalog.return_value = []
    if ai_ready:
        # Async chat call returns a prediction-like object
        pred = MagicMock()
        pred.response = "Hello from AI!"
        pred.component_code = ""
        pred.pipeline_config = ""
        pred.view_stub_request = ""
        mp.ai.chat = AsyncMock(return_value=pred)
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

    # Override the DB dependency so routes use our in-memory DB
    async def _override_get_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session
    app.state.vloop_storage = storage
    app.state.main_process = _make_mock_main_process(ai_ready=False)

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
