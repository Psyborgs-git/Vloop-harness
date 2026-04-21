"""Integration tests for /api/views/* routes.

Uses an in-memory SQLite database and a mocked MainProcess.

Covers:
  - GET  /api/views               (list)
  - POST /api/views/generate      (503 when AI not ready; 201 when AI ready)
  - DELETE /api/views/{id}        (204 + 404)
  - Validation: invalid component names rejected with 422
  - File cleanup on delete
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from harness.data.db import Base, get_session
from harness.data.models import GeneratedView
from harness.data.repository import Repository
from harness.vloop.storage import VLoopStorage


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def views_app(tmp_path: Path):
    """Views-only test app with no AI (engine not ready)."""
    from fastapi import FastAPI

    from harness.server.routes.views_routes import router as views_router

    storage = VLoopStorage(cwd=tmp_path)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    app = FastAPI()
    app.include_router(views_router)

    async def _override():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    app.state.vloop_storage = storage

    mp = MagicMock()
    mp.ai.is_ready = False
    app.state.main_process = mp

    yield app, tmp_path, factory
    await engine.dispose()


@pytest_asyncio.fixture
async def views_client_no_ai(views_app):
    app, tmp_path, factory = views_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, app, factory


@pytest_asyncio.fixture
async def views_app_with_ai(tmp_path: Path):
    """Views-only test app with a mocked AI engine that is ready."""
    from fastapi import FastAPI

    from harness.server.routes.views_routes import router as views_router

    storage = VLoopStorage(cwd=tmp_path)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    app = FastAPI()
    app.include_router(views_router)

    async def _override():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    app.state.vloop_storage = storage

    # Mock a ready AI that returns valid React TSX
    pred = MagicMock()
    pred.react_code = (
        'import { Box } from "@mui/material";\n'
        "export default function GreetCard() {\n"
        '  return <Box>Hello</Box>;\n'
        "}\n"
    )
    pred.component_name = "GreetCard"
    pred.view_spec = "A simple greeting card."

    mp = MagicMock()
    mp.ai.is_ready = True
    mp.ai.generate_view = AsyncMock(return_value=pred)
    app.state.main_process = mp

    yield app, tmp_path, factory
    await engine.dispose()


@pytest_asyncio.fixture
async def views_client_with_ai(views_app_with_ai):
    app, tmp_path, factory = views_app_with_ai
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, app, factory


# ── List views ────────────────────────────────────────────────────────────────


async def test_list_views_empty(views_client_no_ai) -> None:
    client, *_ = views_client_no_ai
    resp = await client.get("/api/views")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_views_returns_saved_records(views_client_no_ai) -> None:
    client, app, factory = views_client_no_ai
    async with factory() as session:
        repo = Repository(session)
        await repo.save_view(
            GeneratedView(
                name="test",
                component_name="TestView",
                react_code="// code",
                view_spec="spec",
            )
        )
    resp = await client.get("/api/views")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["component_name"] == "TestView"


# ── Generate view — no AI ─────────────────────────────────────────────────────


async def test_generate_view_503_when_no_ai(views_client_no_ai) -> None:
    client, *_ = views_client_no_ai
    resp = await client.post(
        "/api/views/generate",
        json={"description": "A dashboard", "component_name": "MyDash"},
    )
    assert resp.status_code == 503
    assert "not configured" in resp.json()["detail"].lower()


# ── Generate view — AI ready ──────────────────────────────────────────────────


async def test_generate_view_201_with_ai(views_client_with_ai) -> None:
    client, *_ = views_client_with_ai
    resp = await client.post(
        "/api/views/generate",
        json={"description": "Greeting card", "component_name": "GreetCard"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["component_name"] == "GreetCard"
    assert "id" in data
    assert "created_at" in data


async def test_generate_view_writes_tsx_file(views_client_with_ai, tmp_path: Path) -> None:
    client, app, _ = views_client_with_ai
    resp = await client.post(
        "/api/views/generate",
        json={"description": "Greeting", "component_name": "GreetCard"},
    )
    assert resp.status_code == 201
    storage = app.state.vloop_storage
    react_root = storage.project_dir.parent / "react" / "src" / "components" / "generated"
    app_file = react_root / "GreetCard" / "App.tsx"
    assert app_file.exists()
    assert "GreetCard" in app_file.read_text()


async def test_generate_view_stores_in_db(views_client_with_ai) -> None:
    client, app, factory = views_client_with_ai
    await client.post(
        "/api/views/generate",
        json={"description": "Widget", "component_name": "GreetCard"},
    )
    async with factory() as session:
        repo = Repository(session)
        views = await repo.list_views()
    assert len(views) == 1
    assert views[0].component_name == "GreetCard"


async def test_generate_view_overrides_name_from_request(views_client_with_ai) -> None:
    """component_name provided in the request must take precedence over AI output."""
    client, *_ = views_client_with_ai
    # The AI would return "GreetCard" but we request "CustomName".
    resp = await client.post(
        "/api/views/generate",
        json={"description": "Custom", "component_name": "CustomName"},
    )
    assert resp.status_code == 201
    assert resp.json()["component_name"] == "CustomName"


# ── Invalid component names rejected ──────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    # Empty string is not tested here: the route falls back to the AI's predicted
    # component_name (GreetCard) when the caller provides empty string.
    ["lowercase", "with-hyphen", "with_underscore", "1StartsWithDigit"],
)
async def test_generate_view_invalid_name_rejected(
    views_client_with_ai, name: str
) -> None:
    client, *_ = views_client_with_ai
    resp = await client.post(
        "/api/views/generate",
        json={"description": "X", "component_name": name},
    )
    assert resp.status_code == 422


# ── Delete view ───────────────────────────────────────────────────────────────


async def test_delete_view_404(views_client_no_ai) -> None:
    client, *_ = views_client_no_ai
    resp = await client.delete("/api/views/no-such-id")
    assert resp.status_code == 404


async def test_delete_view_204(views_client_no_ai) -> None:
    client, app, factory = views_client_no_ai
    async with factory() as session:
        repo = Repository(session)
        v = await repo.save_view(
            GeneratedView(
                name="del",
                component_name="DelView",
                react_code="// code",
                view_spec="",
            )
        )
    resp = await client.delete(f"/api/views/{v.id}")
    assert resp.status_code == 204


async def test_delete_view_removes_from_list(views_client_no_ai) -> None:
    client, app, factory = views_client_no_ai
    async with factory() as session:
        repo = Repository(session)
        v = await repo.save_view(
            GeneratedView(
                name="del",
                component_name="DelView",
                react_code="// code",
                view_spec="",
            )
        )
    await client.delete(f"/api/views/{v.id}")
    resp = await client.get("/api/views")
    assert all(item["id"] != v.id for item in resp.json())


async def test_delete_view_cleans_up_tsx_file(
    views_client_with_ai, tmp_path: Path
) -> None:
    """Deleting a view whose file_path exists must remove the TSX stub."""
    client, app, factory = views_client_with_ai
    # First generate (creates the file)
    await client.post(
        "/api/views/generate",
        json={"description": "Cleanup", "component_name": "GreetCard"},
    )
    storage = app.state.vloop_storage
    react_root = storage.project_dir.parent / "react" / "src" / "components" / "generated"
    app_file = react_root / "GreetCard" / "App.tsx"
    assert app_file.exists()

    # Fetch the view id from DB
    async with factory() as session:
        repo = Repository(session)
        views = await repo.list_views()
    view_id = views[0].id

    await client.delete(f"/api/views/{view_id}")
    assert not app_file.exists()


# ── Response shape ─────────────────────────────────────────────────────────────


async def test_view_response_has_required_fields(views_client_with_ai) -> None:
    client, *_ = views_client_with_ai
    resp = await client.post(
        "/api/views/generate",
        json={"description": "Shape test", "component_name": "GreetCard"},
    )
    data = resp.json()
    for key in (
        "id",
        "name",
        "component_name",
        "react_code",
        "view_spec",
        "file_path",
        "session_id",
        "created_at",
    ):
        assert key in data, f"Missing key: {key}"
