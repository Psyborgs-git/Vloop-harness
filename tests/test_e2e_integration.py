"""End-to-end integration tests for all new harness features.

These tests exercise the actual running backend via HTTP calls.
"""

from __future__ import annotations

import httpx
import pytest

BASE_URL = "http://localhost:9100"


@pytest.fixture
async def client():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as c:
        yield c


class TestHealthAndExistingRoutes:
    @pytest.mark.asyncio
    async def test_root(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "vloop-harness"

    @pytest.mark.asyncio
    async def test_chat_sessions(self, client: httpx.AsyncClient) -> None:
        resp = await client.post("/api/chat/sessions", json={"title": "E2E Test"})
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["title"] == "E2E Test"

    @pytest.mark.asyncio
    async def test_providers(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/providers")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        if len(data) > 0:
            assert "provider_type" in data[0]

    @pytest.mark.asyncio
    async def test_settings(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/settings")
        assert resp.status_code == 200


class TestPipelineRoutes:
    @pytest.mark.asyncio
    async def test_list_templates(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/pipelines/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 5
        ids = [t["id"] for t in data]
        assert "sequential" in ids
        assert "rag" in ids
        assert "agent_loop" in ids

    @pytest.mark.asyncio
    async def test_validate_pipeline(self, client: httpx.AsyncClient) -> None:
        graph = {
            "name": "test",
            "nodes": [
                {"id": "in", "type": "input", "name": "input", "config": {}},
                {"id": "out", "type": "output", "name": "output", "config": {}},
            ],
            "edges": [{"source": "in", "target": "out", "label": "", "input_map": {}}],
        }
        resp = await client.post("/api/pipelines/validate", json={"graph": graph})
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["errors"] == []

    @pytest.mark.asyncio
    async def test_build_sequential(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            "/api/pipelines/build/sequential",
            json={"name": "e2e-seq", "steps": [{"name": "step1", "config": {}}]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "graph" in data
        assert data["validation_errors"] == []


class TestOptimizationRoutes:
    @pytest.mark.asyncio
    async def test_feedback_summary_empty(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/optimization/feedback/comp_nonexistent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0

    @pytest.mark.asyncio
    async def test_submit_feedback(self, client: httpx.AsyncClient) -> None:
        import uuid

        comp_id = f"comp_e2e_{uuid.uuid4().hex[:8]}"
        resp = await client.post(
            "/api/optimization/feedback",
            json={
                "component_id": comp_id,
                "component_name": "E2E Test",
                "input_data": {"q": "hello"},
                "output_data": {"a": "world"},
                "rating": 1,
                "comment": "Great!",
                "tags": ["e2e"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["rating"] == 1
        assert data["component_id"] == comp_id

        # Verify summary updated
        resp = await client.get(f"/api/optimization/feedback/{comp_id}")
        assert resp.status_code == 200
        summary = resp.json()
        assert summary["count"] == 1
        assert summary["avg_rating"] == 1.0


class TestVectorStoreRoutes:
    @pytest.mark.asyncio
    async def test_count_empty(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/vector-store/count")
        assert resp.status_code == 200
        data = resp.json()
        assert "count" in data

    @pytest.mark.asyncio
    async def test_clear(self, client: httpx.AsyncClient) -> None:
        resp = await client.delete("/api/vector-store/clear")
        assert resp.status_code == 200
        data = resp.json()
        assert data["cleared"] is True
