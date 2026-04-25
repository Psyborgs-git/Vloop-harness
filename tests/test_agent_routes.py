"""Integration tests for /api/agents and /api/apps routes.

Uses an in-memory SQLite database and a mock MainProcess.
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
from harness.server.routes.agent_routes import router as agent_router
from harness.server.routes.app_routes import router as app_router


def _mock_mp() -> MagicMock:
    mp = MagicMock()
    mp.ai.is_ready = False
    mp.tools.catalog.return_value = []
    mp.tools.list_tools.return_value = []
    return mp


@pytest_asyncio.fixture
async def app_client() -> AsyncIterator[AsyncClient]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    app = FastAPI()
    app.include_router(agent_router)
    app.include_router(app_router)

    async def _override() -> AsyncIterator[AsyncSession]:
        async with factory() as s:
            yield s

    app.dependency_overrides[get_session] = _override
    app.state.main_process = _mock_mp()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client

    await engine.dispose()


# ── Agent run routes ───────────────────────────────────────────────────────────


class TestAgentRunRoutes:
    async def test_start_run_201(self, app_client: AsyncClient) -> None:
        resp = await app_client.post(
            "/api/agents/runs",
            json={"goal": "Build a thing", "autonomy_mode": "observe"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["goal"] == "Build a thing"
        assert data["status"] in ("pending", "running")
        assert "id" in data

    async def test_list_runs(self, app_client: AsyncClient) -> None:
        await app_client.post(
            "/api/agents/runs", json={"goal": "First run"}
        )
        resp = await app_client.get("/api/agents/runs")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        assert len(resp.json()) >= 1

    async def test_get_run(self, app_client: AsyncClient) -> None:
        create_resp = await app_client.post(
            "/api/agents/runs", json={"goal": "Get me"}
        )
        run_id = create_resp.json()["id"]
        resp = await app_client.get(f"/api/agents/runs/{run_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == run_id
        assert "steps" in resp.json()

    async def test_get_run_404(self, app_client: AsyncClient) -> None:
        resp = await app_client.get("/api/agents/runs/nonexistent-id")
        assert resp.status_code == 404

    async def test_cancel_run(self, app_client: AsyncClient) -> None:
        create_resp = await app_client.post(
            "/api/agents/runs", json={"goal": "Cancel me"}
        )
        run_id = create_resp.json()["id"]
        resp = await app_client.post(f"/api/agents/runs/{run_id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    async def test_delete_run(self, app_client: AsyncClient) -> None:
        create_resp = await app_client.post(
            "/api/agents/runs", json={"goal": "Delete me"}
        )
        run_id = create_resp.json()["id"]
        del_resp = await app_client.delete(f"/api/agents/runs/{run_id}")
        assert del_resp.status_code == 204
        get_resp = await app_client.get(f"/api/agents/runs/{run_id}")
        assert get_resp.status_code == 404


# ── App manifest routes ────────────────────────────────────────────────────────


class TestAppManifestRoutes:
    async def test_create_201(self, app_client: AsyncClient) -> None:
        resp = await app_client.post(
            "/api/apps/manifests",
            json={
                "name": "My App",
                "backend_type": "pipeline",
                "react_views": ["ViewA"],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "My App"
        assert data["status"] == "draft"
        assert data["react_views"] == ["ViewA"]

    async def test_list_manifests(self, app_client: AsyncClient) -> None:
        await app_client.post("/api/apps/manifests", json={"name": "App1"})
        await app_client.post("/api/apps/manifests", json={"name": "App2"})
        resp = await app_client.get("/api/apps/manifests")
        assert resp.status_code == 200
        assert len(resp.json()) >= 2

    async def test_get_manifest(self, app_client: AsyncClient) -> None:
        create = await app_client.post("/api/apps/manifests", json={"name": "Get me"})
        m_id = create.json()["id"]
        resp = await app_client.get(f"/api/apps/manifests/{m_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == m_id

    async def test_get_manifest_404(self, app_client: AsyncClient) -> None:
        resp = await app_client.get("/api/apps/manifests/no-such-id")
        assert resp.status_code == 404

    async def test_promote_status(self, app_client: AsyncClient) -> None:
        create = await app_client.post("/api/apps/manifests", json={"name": "Promote me"})
        m_id = create.json()["id"]
        resp = await app_client.post(
            f"/api/apps/manifests/{m_id}/promote",
            json={"status": "validated"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "validated"

    async def test_promote_invalid_status(self, app_client: AsyncClient) -> None:
        create = await app_client.post("/api/apps/manifests", json={"name": "Bad status"})
        m_id = create.json()["id"]
        resp = await app_client.post(
            f"/api/apps/manifests/{m_id}/promote",
            json={"status": "invalid_status"},
        )
        assert resp.status_code == 422

    async def test_update_manifest(self, app_client: AsyncClient) -> None:
        create = await app_client.post("/api/apps/manifests", json={"name": "Update me"})
        m_id = create.json()["id"]
        resp = await app_client.put(
            f"/api/apps/manifests/{m_id}",
            json={"description": "Updated description"},
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "Updated description"

    async def test_delete_manifest(self, app_client: AsyncClient) -> None:
        create = await app_client.post("/api/apps/manifests", json={"name": "Delete me"})
        m_id = create.json()["id"]
        del_resp = await app_client.delete(f"/api/apps/manifests/{m_id}")
        assert del_resp.status_code == 204
        get_resp = await app_client.get(f"/api/apps/manifests/{m_id}")
        assert get_resp.status_code == 404

    async def test_filter_manifests_by_status(self, app_client: AsyncClient) -> None:
        create = await app_client.post("/api/apps/manifests", json={"name": "Active one"})
        m_id = create.json()["id"]
        await app_client.post(
            f"/api/apps/manifests/{m_id}/promote", json={"status": "active"}
        )
        resp = await app_client.get("/api/apps/manifests?status=active")
        assert resp.status_code == 200
        assert all(m["status"] == "active" for m in resp.json())

    async def test_list_traces_empty(self, app_client: AsyncClient) -> None:
        resp = await app_client.get("/api/apps/traces")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_ui_contract_manifest_react_views_produce_stable_workspace_url(
        self, app_client: AsyncClient
    ) -> None:
        """UI contract: workspace-open URL is derived from first react view."""
        create = await app_client.post(
            "/api/apps/manifests",
            json={
                "name": "Finance Cockpit",
                "status": "active",
                "react_views": ["RevenueDashboard", "OpsView"],
            },
        )
        assert create.status_code == 201
        manifest_id = create.json()["id"]

        get_resp = await app_client.get(f"/api/apps/manifests/{manifest_id}")
        assert get_resp.status_code == 200
        manifest = get_resp.json()

        # Matches AppManifestPanel's `href={`/ui/${m.react_views[0]}`}` contract.
        first_view_url = f"/ui/{manifest['react_views'][0]}"
        assert first_view_url == "/ui/RevenueDashboard"
