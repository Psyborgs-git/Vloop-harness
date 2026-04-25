"""Tests for Phase 6 additions: component versioning, eval datasets, and secret redaction.

Covers
──────
  harness.vloop.redaction.redact_secrets
  Repository.create_component_version / list / get
  Repository.create_eval_dataset / list / get / update / delete
  GET/POST /api/dspy/components/{id}/versions
  POST     /api/dspy/components/{id}/snapshot
  POST     /api/dspy/components/{id}/rollback
  GET/POST /api/dspy/components/{id}/eval-datasets
  PUT/DELETE /api/dspy/components/{id}/eval-datasets/{did}
  POST     /api/dspy/components/{id}/evaluate
"""

from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from harness.data.db import Base, get_session
from harness.data.models import DSPyComponentDef
from harness.data.repository import Repository
from harness.vloop.redaction import redact_secrets


# ── In-memory DB fixtures ─────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
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


# ── Helpers ───────────────────────────────────────────────────────────────────

_SAMPLE_CODE = """
import dspy

class QA(dspy.Signature):
    question: str = dspy.InputField()
    answer: str = dspy.OutputField()

class QAModule(dspy.Module):
    def __init__(self):
        self.prog = dspy.ChainOfThought(QA)
    def forward(self, question):
        return self.prog(question=question)
"""


async def _make_component(repo: Repository, name: str = "QA") -> DSPyComponentDef:
    comp = DSPyComponentDef(
        id=f"comp_{name.lower()}",
        name=name,
        description="Test component",
        code=_SAMPLE_CODE,
        module_type="ChainOfThought",
        signature_fields={},
    )
    return await repo.save_component(comp)


# ── Secret redaction unit tests ───────────────────────────────────────────────


class TestRedactSecrets:
    def test_plain_dict_no_secrets(self) -> None:
        data = {"foo": "bar", "count": 42}
        assert redact_secrets(data) == {"foo": "bar", "count": 42}

    def test_api_key_redacted(self) -> None:
        data = {"api_key": "sk-secret123", "model": "gpt-4"}
        result = redact_secrets(data)
        assert result["api_key"] == "[REDACTED]"
        assert result["model"] == "gpt-4"

    def test_password_redacted(self) -> None:
        result = redact_secrets({"password": "hunter2"})
        assert result["password"] == "[REDACTED]"

    def test_token_redacted(self) -> None:
        result = redact_secrets({"token": "abc123"})
        assert result["token"] == "[REDACTED]"

    def test_secret_redacted(self) -> None:
        result = redact_secrets({"secret": "topsecret"})
        assert result["secret"] == "[REDACTED]"

    def test_authorization_header_redacted(self) -> None:
        result = redact_secrets({"Authorization": "Bearer xyz"})
        assert result["Authorization"] == "[REDACTED]"

    def test_bearer_key_redacted(self) -> None:
        result = redact_secrets({"bearer_token": "abc"})
        assert result["bearer_token"] == "[REDACTED]"

    def test_case_insensitive_match(self) -> None:
        result = redact_secrets({"API_KEY": "secret", "Password": "pass"})
        assert result["API_KEY"] == "[REDACTED]"
        assert result["Password"] == "[REDACTED]"

    def test_nested_dict_redacted(self) -> None:
        data = {"config": {"api_key": "val", "timeout": 30}}
        result = redact_secrets(data)
        assert result["config"]["api_key"] == "[REDACTED]"
        assert result["config"]["timeout"] == 30

    def test_list_passthrough(self) -> None:
        data = [{"api_key": "x"}, {"name": "y"}]
        result = redact_secrets(data)
        assert result[0]["api_key"] == "[REDACTED]"
        assert result[1]["name"] == "y"

    def test_string_passthrough(self) -> None:
        assert redact_secrets("hello") == "hello"

    def test_none_passthrough(self) -> None:
        assert redact_secrets(None) is None

    def test_int_passthrough(self) -> None:
        assert redact_secrets(42) == 42

    def test_large_string_truncated(self) -> None:
        big = "x" * (8 * 1024 + 100)
        result = redact_secrets(big)
        assert result.endswith("…[truncated]")
        assert len(result) < len(big)

    def test_large_value_in_dict_truncated(self) -> None:
        data = {"output": "a" * (8 * 1024 + 1)}
        result = redact_secrets(data)
        assert result["output"].endswith("…[truncated]")

    def test_credential_redacted(self) -> None:
        result = redact_secrets({"db_credential": "root:pass"})
        assert result["db_credential"] == "[REDACTED]"

    def test_auth_key_redacted(self) -> None:
        result = redact_secrets({"auth_header": "Basic dXNlcjpwYXNz"})
        assert result["auth_header"] == "[REDACTED]"


# ── Repository: ComponentVersion ──────────────────────────────────────────────


class TestComponentVersionRepository:
    async def test_create_first_version_is_1(self, repo: Repository) -> None:
        comp = await _make_component(repo)
        v = await repo.create_component_version(
            component_id=comp.id,
            name=comp.name,
            code=comp.code,
        )
        assert v.version_number == 1
        assert v.component_id == comp.id

    async def test_version_number_increments(self, repo: Repository) -> None:
        comp = await _make_component(repo)
        v1 = await repo.create_component_version(component_id=comp.id, name="v1", code="c1")
        v2 = await repo.create_component_version(component_id=comp.id, name="v2", code="c2")
        assert v2.version_number == v1.version_number + 1

    async def test_list_versions_ordered_desc(self, repo: Repository) -> None:
        comp = await _make_component(repo)
        for i in range(3):
            await repo.create_component_version(
                component_id=comp.id, name=f"v{i}", code=f"code{i}"
            )
        versions = await repo.list_component_versions(comp.id)
        numbers = [v.version_number for v in versions]
        assert numbers == sorted(numbers, reverse=True)

    async def test_list_versions_empty_for_unknown_component(self, repo: Repository) -> None:
        versions = await repo.list_component_versions("nonexistent")
        assert versions == []

    async def test_get_version_by_id(self, repo: Repository) -> None:
        comp = await _make_component(repo)
        v = await repo.create_component_version(
            component_id=comp.id, name="snap", code="code", change_summary="initial"
        )
        fetched = await repo.get_component_version(v.id)
        assert fetched is not None
        assert fetched.id == v.id
        assert fetched.change_summary == "initial"

    async def test_get_version_missing_returns_none(self, repo: Repository) -> None:
        result = await repo.get_component_version("ghost-version-id")
        assert result is None

    async def test_change_summary_stored(self, repo: Repository) -> None:
        comp = await _make_component(repo)
        v = await repo.create_component_version(
            component_id=comp.id, name="x", code="y", change_summary="Fixed a bug"
        )
        assert v.change_summary == "Fixed a bug"

    async def test_versions_isolated_per_component(self, repo: Repository) -> None:
        c1 = await _make_component(repo, "C1")
        c2 = await _make_component(repo, "C2")
        await repo.create_component_version(component_id=c1.id, name="c1v1", code="a")
        await repo.create_component_version(component_id=c1.id, name="c1v2", code="b")
        await repo.create_component_version(component_id=c2.id, name="c2v1", code="x")

        c1_versions = await repo.list_component_versions(c1.id)
        c2_versions = await repo.list_component_versions(c2.id)
        assert len(c1_versions) == 2
        assert len(c2_versions) == 1
        assert c2_versions[0].version_number == 1


# ── Repository: EvalDataset ───────────────────────────────────────────────────


class TestEvalDatasetRepository:
    async def test_create_dataset(self, repo: Repository) -> None:
        comp = await _make_component(repo)
        ds = await repo.create_eval_dataset(
            component_id=comp.id,
            name="Basic QA",
            examples=[{"inputs": {"question": "Hi"}, "expected_outputs": {"answer": "Hello"}}],
        )
        assert ds.id
        assert ds.name == "Basic QA"
        assert len(ds.examples) == 1

    async def test_create_dataset_empty_examples(self, repo: Repository) -> None:
        comp = await _make_component(repo)
        ds = await repo.create_eval_dataset(component_id=comp.id, name="Empty")
        assert ds.examples == []

    async def test_list_datasets(self, repo: Repository) -> None:
        comp = await _make_component(repo)
        await repo.create_eval_dataset(component_id=comp.id, name="DS1")
        await repo.create_eval_dataset(component_id=comp.id, name="DS2")
        datasets = await repo.list_eval_datasets(comp.id)
        assert len(datasets) == 2

    async def test_list_datasets_empty(self, repo: Repository) -> None:
        assert await repo.list_eval_datasets("nonexistent") == []

    async def test_get_dataset(self, repo: Repository) -> None:
        comp = await _make_component(repo)
        ds = await repo.create_eval_dataset(component_id=comp.id, name="Get me")
        fetched = await repo.get_eval_dataset(ds.id)
        assert fetched is not None
        assert fetched.name == "Get me"

    async def test_get_dataset_missing(self, repo: Repository) -> None:
        assert await repo.get_eval_dataset("ghost") is None

    async def test_update_dataset_name(self, repo: Repository) -> None:
        comp = await _make_component(repo)
        ds = await repo.create_eval_dataset(component_id=comp.id, name="Old")
        await repo.update_eval_dataset(ds.id, name="New")
        refreshed = await repo.get_eval_dataset(ds.id)
        assert refreshed.name == "New"

    async def test_update_dataset_examples(self, repo: Repository) -> None:
        comp = await _make_component(repo)
        ds = await repo.create_eval_dataset(component_id=comp.id, name="DS", examples=[])
        new_examples = [{"inputs": {"q": "x"}, "expected_outputs": {"a": "y"}}]
        await repo.update_eval_dataset(ds.id, examples=new_examples)
        refreshed = await repo.get_eval_dataset(ds.id)
        assert len(refreshed.examples) == 1

    async def test_delete_dataset(self, repo: Repository) -> None:
        comp = await _make_component(repo)
        ds = await repo.create_eval_dataset(component_id=comp.id, name="ToDelete")
        await repo.delete_eval_dataset(ds.id)
        assert await repo.get_eval_dataset(ds.id) is None

    async def test_delete_nonexistent_is_safe(self, repo: Repository) -> None:
        await repo.delete_eval_dataset("ghost")  # Must not raise


# ── Eval routes integration tests ─────────────────────────────────────────────


@pytest_asyncio.fixture
async def eval_app(tmp_path: Path):
    """Minimal FastAPI app with dspy + eval routers and a mock registry."""
    from harness.server.routes.dspy_routes import router as dspy_router
    from harness.server.routes.eval_routes import router as eval_router

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    app = FastAPI()
    app.include_router(dspy_router)
    app.include_router(eval_router)

    async def _override() -> AsyncIterator[AsyncSession]:
        async with factory() as s:
            yield s

    app.dependency_overrides[get_session] = _override

    # Mock registry: compile is a no-op, is_loaded always False initially
    registry = MagicMock()
    registry.is_loaded.return_value = False
    registry.compile.return_value = None
    registry.unload.return_value = None
    app.state.component_registry = registry
    app.state.pipeline_builder = MagicMock()

    yield app, factory, registry
    await engine.dispose()


@pytest_asyncio.fixture
async def eval_client(eval_app):
    app, factory, registry = eval_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, factory, registry


async def _create_component_via_api(client: AsyncClient) -> dict:
    """Helper to POST a component and return the JSON body."""
    resp = await client.post(
        "/api/dspy/components",
        json={
            "name": "QAComp",
            "description": "Test",
            "code": _SAMPLE_CODE,
            "module_type": "ChainOfThought",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── Version endpoint tests ────────────────────────────────────────────────────


class TestVersionEndpoints:
    async def test_list_versions_empty(self, eval_client) -> None:
        client, factory, _ = eval_client
        comp = await _create_component_via_api(client)
        resp = await client.get(f"/api/dspy/components/{comp['id']}/versions")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_versions_404_unknown_component(self, eval_client) -> None:
        client, *_ = eval_client
        resp = await client.get("/api/dspy/components/nope/versions")
        assert resp.status_code == 404

    async def test_snapshot_creates_version(self, eval_client) -> None:
        client, *_ = eval_client
        comp = await _create_component_via_api(client)
        resp = await client.post(
            f"/api/dspy/components/{comp['id']}/snapshot",
            json={"change_summary": "Initial snapshot"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["version_number"] == 1
        assert data["change_summary"] == "Initial snapshot"
        assert data["component_id"] == comp["id"]

    async def test_snapshot_version_numbers_increment(self, eval_client) -> None:
        client, *_ = eval_client
        comp = await _create_component_via_api(client)
        cid = comp["id"]
        await client.post(f"/api/dspy/components/{cid}/snapshot", json={})
        r2 = await client.post(f"/api/dspy/components/{cid}/snapshot", json={})
        assert r2.json()["version_number"] == 2

    async def test_snapshot_404_unknown_component(self, eval_client) -> None:
        client, *_ = eval_client
        resp = await client.post("/api/dspy/components/nope/snapshot", json={})
        assert resp.status_code == 404

    async def test_list_versions_after_snapshots(self, eval_client) -> None:
        client, *_ = eval_client
        comp = await _create_component_via_api(client)
        cid = comp["id"]
        for _ in range(3):
            await client.post(f"/api/dspy/components/{cid}/snapshot", json={})
        resp = await client.get(f"/api/dspy/components/{cid}/versions")
        assert resp.status_code == 200
        assert len(resp.json()) == 3

    async def test_versions_ordered_desc(self, eval_client) -> None:
        client, *_ = eval_client
        comp = await _create_component_via_api(client)
        cid = comp["id"]
        for _ in range(3):
            await client.post(f"/api/dspy/components/{cid}/snapshot", json={})
        versions = (await client.get(f"/api/dspy/components/{cid}/versions")).json()
        nums = [v["version_number"] for v in versions]
        assert nums == sorted(nums, reverse=True)

    async def test_version_response_shape(self, eval_client) -> None:
        client, *_ = eval_client
        comp = await _create_component_via_api(client)
        await client.post(f"/api/dspy/components/{comp['id']}/snapshot", json={})
        versions = (await client.get(f"/api/dspy/components/{comp['id']}/versions")).json()
        for key in ("id", "component_id", "version_number", "name", "code", "module_type",
                    "change_summary", "created_at"):
            assert key in versions[0], f"Missing key: {key}"


# ── Rollback endpoint tests ───────────────────────────────────────────────────


class TestRollbackEndpoint:
    async def test_rollback_applies_version_fields(self, eval_client) -> None:
        client, factory, _ = eval_client
        comp = await _create_component_via_api(client)
        cid = comp["id"]

        # Snapshot initial state
        snap = (await client.post(
            f"/api/dspy/components/{cid}/snapshot",
            json={"change_summary": "before update"},
        )).json()

        # Update the component
        await client.put(f"/api/dspy/components/{cid}", json={"name": "UpdatedName"})

        # Rollback to original snapshot
        resp = await client.post(
            f"/api/dspy/components/{cid}/rollback",
            json={"version_id": snap["id"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["component"]["name"] == "QAComp"  # restored
        assert data["rolled_back_to"] == snap["id"]

    async def test_rollback_creates_pre_rollback_snapshot(self, eval_client) -> None:
        client, factory, _ = eval_client
        comp = await _create_component_via_api(client)
        cid = comp["id"]
        snap = (await client.post(f"/api/dspy/components/{cid}/snapshot", json={})).json()

        await client.post(
            f"/api/dspy/components/{cid}/rollback",
            json={"version_id": snap["id"]},
        )
        versions = (await client.get(f"/api/dspy/components/{cid}/versions")).json()
        summaries = [v["change_summary"] for v in versions]
        assert "pre-rollback snapshot" in summaries

    async def test_rollback_404_unknown_component(self, eval_client) -> None:
        client, *_ = eval_client
        resp = await client.post(
            "/api/dspy/components/nope/rollback",
            json={"version_id": "some-id"},
        )
        assert resp.status_code == 404

    async def test_rollback_404_unknown_version(self, eval_client) -> None:
        client, *_ = eval_client
        comp = await _create_component_via_api(client)
        resp = await client.post(
            f"/api/dspy/components/{comp['id']}/rollback",
            json={"version_id": "ghost-version"},
        )
        assert resp.status_code == 404

    async def test_rollback_404_version_belongs_to_other_component(
        self, eval_client
    ) -> None:
        client, factory, _ = eval_client
        c1 = await _create_component_via_api(client)

        # Create second component (needs a unique id)
        resp = await client.post(
            "/api/dspy/components",
            json={"name": "OtherComp", "description": "", "code": _SAMPLE_CODE},
        )
        assert resp.status_code == 201
        c2 = resp.json()

        snap = (await client.post(f"/api/dspy/components/{c2['id']}/snapshot", json={})).json()
        resp = await client.post(
            f"/api/dspy/components/{c1['id']}/rollback",
            json={"version_id": snap["id"]},
        )
        assert resp.status_code == 404


# ── Eval dataset endpoint tests ───────────────────────────────────────────────


class TestEvalDatasetEndpoints:
    async def test_list_eval_datasets_empty(self, eval_client) -> None:
        client, *_ = eval_client
        comp = await _create_component_via_api(client)
        resp = await client.get(f"/api/dspy/components/{comp['id']}/eval-datasets")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_eval_datasets_404_unknown_component(self, eval_client) -> None:
        client, *_ = eval_client
        resp = await client.get("/api/dspy/components/nope/eval-datasets")
        assert resp.status_code == 404

    async def test_create_eval_dataset(self, eval_client) -> None:
        client, *_ = eval_client
        comp = await _create_component_via_api(client)
        resp = await client.post(
            f"/api/dspy/components/{comp['id']}/eval-datasets",
            json={
                "name": "QA set",
                "description": "Basic QA pairs",
                "examples": [{"inputs": {"question": "Hi"}, "expected_outputs": {"answer": "Hello"}}],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "QA set"
        assert len(data["examples"]) == 1

    async def test_create_eval_dataset_404_unknown_component(self, eval_client) -> None:
        client, *_ = eval_client
        resp = await client.post(
            "/api/dspy/components/nope/eval-datasets",
            json={"name": "DS"},
        )
        assert resp.status_code == 404

    async def test_create_eval_dataset_response_shape(self, eval_client) -> None:
        client, *_ = eval_client
        comp = await _create_component_via_api(client)
        resp = await client.post(
            f"/api/dspy/components/{comp['id']}/eval-datasets",
            json={"name": "DS"},
        )
        data = resp.json()
        for key in ("id", "component_id", "name", "description", "examples",
                    "created_at", "updated_at"):
            assert key in data, f"Missing key: {key}"

    async def test_update_eval_dataset_name(self, eval_client) -> None:
        client, *_ = eval_client
        comp = await _create_component_via_api(client)
        cid = comp["id"]
        ds = (await client.post(
            f"/api/dspy/components/{cid}/eval-datasets",
            json={"name": "Old"},
        )).json()
        resp = await client.put(
            f"/api/dspy/components/{cid}/eval-datasets/{ds['id']}",
            json={"name": "New"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New"

    async def test_update_eval_dataset_examples(self, eval_client) -> None:
        client, *_ = eval_client
        comp = await _create_component_via_api(client)
        cid = comp["id"]
        ds = (await client.post(
            f"/api/dspy/components/{cid}/eval-datasets",
            json={"name": "DS", "examples": []},
        )).json()
        new_ex = [{"inputs": {"q": "hi"}, "expected_outputs": {"a": "hello"}}]
        resp = await client.put(
            f"/api/dspy/components/{cid}/eval-datasets/{ds['id']}",
            json={"examples": new_ex},
        )
        assert resp.status_code == 200
        assert len(resp.json()["examples"]) == 1

    async def test_update_eval_dataset_404(self, eval_client) -> None:
        client, *_ = eval_client
        comp = await _create_component_via_api(client)
        resp = await client.put(
            f"/api/dspy/components/{comp['id']}/eval-datasets/ghost",
            json={"name": "X"},
        )
        assert resp.status_code == 404

    async def test_update_dataset_wrong_component_404(self, eval_client) -> None:
        client, *_ = eval_client
        c1 = await _create_component_via_api(client)
        resp2 = await client.post(
            "/api/dspy/components",
            json={"name": "OtherComp", "description": "", "code": _SAMPLE_CODE},
        )
        c2 = resp2.json()
        ds = (await client.post(
            f"/api/dspy/components/{c2['id']}/eval-datasets",
            json={"name": "DS"},
        )).json()
        resp = await client.put(
            f"/api/dspy/components/{c1['id']}/eval-datasets/{ds['id']}",
            json={"name": "Hack"},
        )
        assert resp.status_code == 404

    async def test_delete_eval_dataset(self, eval_client) -> None:
        client, *_ = eval_client
        comp = await _create_component_via_api(client)
        cid = comp["id"]
        ds = (await client.post(
            f"/api/dspy/components/{cid}/eval-datasets",
            json={"name": "Del"},
        )).json()
        resp = await client.delete(
            f"/api/dspy/components/{cid}/eval-datasets/{ds['id']}"
        )
        assert resp.status_code == 204
        resp2 = await client.get(f"/api/dspy/components/{cid}/eval-datasets")
        assert all(d["id"] != ds["id"] for d in resp2.json())

    async def test_delete_eval_dataset_404(self, eval_client) -> None:
        client, *_ = eval_client
        comp = await _create_component_via_api(client)
        resp = await client.delete(
            f"/api/dspy/components/{comp['id']}/eval-datasets/ghost"
        )
        assert resp.status_code == 404


# ── Evaluate endpoint tests ───────────────────────────────────────────────────


class TestEvaluateEndpoint:
    async def test_evaluate_404_no_datasets(self, eval_client) -> None:
        client, *_ = eval_client
        comp = await _create_component_via_api(client)
        resp = await client.post(
            f"/api/dspy/components/{comp['id']}/evaluate",
            json={},
        )
        assert resp.status_code == 404

    async def test_evaluate_404_unknown_component(self, eval_client) -> None:
        client, *_ = eval_client
        resp = await client.post(
            "/api/dspy/components/nope/evaluate",
            json={},
        )
        assert resp.status_code == 404

    async def test_evaluate_404_unknown_dataset(self, eval_client) -> None:
        client, *_ = eval_client
        comp = await _create_component_via_api(client)
        resp = await client.post(
            f"/api/dspy/components/{comp['id']}/evaluate",
            json={"dataset_id": "ghost"},
        )
        assert resp.status_code == 404

    async def test_evaluate_response_shape_with_mock(self, eval_client) -> None:
        """All examples pass when module output matches expected (mocked module)."""
        client, factory, registry = eval_client

        comp = await _create_component_via_api(client)
        cid = comp["id"]

        # Create a dataset with one example
        ds = (await client.post(
            f"/api/dspy/components/{cid}/eval-datasets",
            json={
                "name": "Test DS",
                "examples": [
                    {
                        "inputs": {"question": "What is 2+2?"},
                        "expected_outputs": {"answer": "4"},
                    }
                ],
            },
        )).json()

        # Mock module: returns prediction with answer == "4"
        pred = MagicMock()
        pred.toDict.return_value = {"answer": "4"}
        mock_module = MagicMock(return_value=pred)
        registry.instantiate.return_value = mock_module

        resp = await client.post(
            f"/api/dspy/components/{cid}/evaluate",
            json={"dataset_id": ds["id"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["passed"] == 1
        assert data["failed"] == 0
        assert len(data["results"]) == 1
        assert data["results"][0]["passed"] is True

    async def test_evaluate_case_insensitive_match(self, eval_client) -> None:
        client, factory, registry = eval_client
        comp = await _create_component_via_api(client)
        cid = comp["id"]

        ds = (await client.post(
            f"/api/dspy/components/{cid}/eval-datasets",
            json={
                "name": "DS",
                "examples": [
                    {"inputs": {"q": "x"}, "expected_outputs": {"answer": "Hello World"}},
                ],
            },
        )).json()

        pred = MagicMock()
        pred.toDict.return_value = {"answer": "hello world"}  # different case
        registry.instantiate.return_value = MagicMock(return_value=pred)

        resp = await client.post(
            f"/api/dspy/components/{cid}/evaluate",
            json={"dataset_id": ds["id"]},
        )
        assert resp.json()["passed"] == 1

    async def test_evaluate_failed_example(self, eval_client) -> None:
        client, factory, registry = eval_client
        comp = await _create_component_via_api(client)
        cid = comp["id"]

        ds = (await client.post(
            f"/api/dspy/components/{cid}/eval-datasets",
            json={
                "name": "DS",
                "examples": [
                    {"inputs": {"q": "x"}, "expected_outputs": {"answer": "correct"}},
                ],
            },
        )).json()

        pred = MagicMock()
        pred.toDict.return_value = {"answer": "wrong"}
        registry.instantiate.return_value = MagicMock(return_value=pred)

        resp = await client.post(
            f"/api/dspy/components/{cid}/evaluate",
            json={"dataset_id": ds["id"]},
        )
        data = resp.json()
        assert data["passed"] == 0
        assert data["failed"] == 1
        assert data["results"][0]["passed"] is False

    async def test_evaluate_uses_most_recent_dataset_when_no_id(
        self, eval_client
    ) -> None:
        client, factory, registry = eval_client
        comp = await _create_component_via_api(client)
        cid = comp["id"]

        ds = (await client.post(
            f"/api/dspy/components/{cid}/eval-datasets",
            json={
                "name": "Auto DS",
                "examples": [
                    {"inputs": {"q": "hi"}, "expected_outputs": {"answer": "hello"}}
                ],
            },
        )).json()

        pred = MagicMock()
        pred.toDict.return_value = {"answer": "hello"}
        registry.instantiate.return_value = MagicMock(return_value=pred)

        resp = await client.post(
            f"/api/dspy/components/{cid}/evaluate",
            json={},  # no dataset_id
        )
        assert resp.status_code == 200
        assert resp.json()["dataset_id"] == ds["id"]

    async def test_evaluate_result_contains_field_results(self, eval_client) -> None:
        client, factory, registry = eval_client
        comp = await _create_component_via_api(client)
        cid = comp["id"]

        ds = (await client.post(
            f"/api/dspy/components/{cid}/eval-datasets",
            json={
                "name": "DS",
                "examples": [
                    {"inputs": {"q": "1"}, "expected_outputs": {"a": "x", "b": "y"}},
                ],
            },
        )).json()

        pred = MagicMock()
        pred.toDict.return_value = {"a": "x", "b": "wrong"}
        registry.instantiate.return_value = MagicMock(return_value=pred)

        resp = await client.post(
            f"/api/dspy/components/{cid}/evaluate",
            json={"dataset_id": ds["id"]},
        )
        result = resp.json()["results"][0]
        assert result["field_results"]["a"] is True
        assert result["field_results"]["b"] is False
        assert result["passed"] is False
