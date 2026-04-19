"""Smoke tests for inference-backend."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch


@pytest.fixture()
def client():
    # Patch LM config so tests don't require Ollama
    with patch("inference_backend.dspy_core.lm_config.configure_lm"):
        from inference_backend.main import app
        with TestClient(app) as c:
            yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"


def test_agent_loops_list(client):
    r = client.get("/agent/loops")
    assert r.status_code == 200
    loops = r.json()
    assert "chain_of_thought" in loops
    assert "react" in loops
    assert "plan_execute" in loops
    assert "tool_call" in loops
    assert "multi_agent" in loops


def test_module_list(client):
    r = client.get("/module/list")
    assert r.status_code == 200


def test_pipeline_list(client):
    r = client.get("/pipeline/list")
    assert r.status_code == 200


def test_module_invalid_code(client):
    r = client.post("/module/create", json={"name": "bad_mod", "code": "def )(:"})
    assert r.status_code == 400


def test_self_modify_validator_syntax_error():
    from inference_backend.self_modify.validator import validate_syntax
    ok, msg = validate_syntax("def bad():")
    assert not ok
    assert "SyntaxError" in msg


def test_self_modify_validator_valid():
    from inference_backend.self_modify.validator import validate_syntax
    ok, msg = validate_syntax("def good():\n    return 42\n")
    assert ok
    assert msg == ""
