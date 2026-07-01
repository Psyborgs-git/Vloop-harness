"""Tests for wiring the Inference_Gateway into agent invocation (task 17.5).

These cover the integration point added by task 17.5: routing existing agent
model calls through :meth:`InferenceGateway.call` so every model call passes the
gateway's policy layer (routing/budget/cache/retry/fallback), with no orphaned
direct provider call remaining (Req 6.1), while invocation and usage recording
continue exactly as before (Req 5.4).

The real DSPy/``build_lm`` execution is stubbed so these tests deterministically
exercise the wiring (does the model call flow through ``gateway.call``? are the
structured outputs and usage recorded?) without depending on a live model.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

import core.agent_invoker as agent_invoker
from core.agent_invoker import execute_invocation
from core.agent_orchestrator import AgentOrchestrator
from core.database import SQLiteBackend
from core.event_router import EventRouter
from core.helpers import now_iso, to_json
from core.inference_gateway import InferenceGateway, ModelResponse
from core.orchestration_types import ModelRequest, RoutingPolicy, RunScope
from core.provider_router import ProviderRouter
from core.provider_service import ProviderService

_STUB_OUTPUT = ("echoed: hello", None, "stub reasoning", {
    "prompt_tokens": 3,
    "completion_tokens": 5,
    "total_tokens": 8,
    "model": "mock/echo",
})


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def backend(tmp_path: Path) -> SQLiteBackend:
    return SQLiteBackend(tmp_path / "agent-gateway.db")


@pytest.fixture()
def providers(backend: SQLiteBackend) -> ProviderService:
    return ProviderService(backend)


@pytest.fixture()
def provider(providers: ProviderService) -> dict[str, Any]:
    return providers.save_provider(
        {"name": "Mock Provider", "providerType": "mock", "defaultModel": "mock/echo"}
    )


@pytest.fixture()
def agent(
    backend: SQLiteBackend, providers: ProviderService, provider: dict[str, Any]
) -> dict[str, Any]:
    orchestrator = AgentOrchestrator(backend, providers)
    return orchestrator.save_agent(
        {
            "name": "Echo Agent",
            "instructions": "You echo the user's request back to them.",
            "inputFields": [{"name": "prompt", "label": "Prompt"}],
            "defaultProviderId": provider["id"],
        }
    )


@pytest.fixture(autouse=True)
def stub_model_execution(monkeypatch: pytest.MonkeyPatch):
    """Stub build_lm + the DSPy program so the model call is deterministic.

    Records each provider id that the (stubbed) real provider call is invoked
    with, so tests can assert the call actually reached the provider step after
    flowing through the gateway pipeline.
    """
    seen_provider_ids: list[str] = []

    def _fake_build_lm(self, provider_id, **_kwargs):
        seen_provider_ids.append(provider_id)
        return object()  # opaque LM handle; the DSPy program is stubbed below

    def _fake_run_dspy_program(_agent, _lm, _request_text):
        return _STUB_OUTPUT

    monkeypatch.setattr(ProviderService, "build_lm", _fake_build_lm, raising=True)
    monkeypatch.setattr(
        agent_invoker, "_run_dspy_program", _fake_run_dspy_program, raising=True
    )
    return seen_provider_ids


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_invocation(
    backend: SQLiteBackend,
    invocation_id: str,
    agent: dict[str, Any],
    provider: dict[str, Any],
    inputs: dict[str, Any],
) -> None:
    """Insert a queued invocation row mirroring ``AgentOrchestrator.invoke_agent``."""
    backend.execute(
        """
        INSERT INTO invocations (
            id, agent_id, agent_revision, provider_id, provider_revision, status,
            inputs_json, overrides_json, resolved_model, resolved_config_json,
            output_text, output_json, reasoning_text, usage_json, error_code,
            error_message, created_at, started_at, finished_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            invocation_id,
            agent["id"],
            agent["revision"],
            provider["id"],
            provider["revision"],
            "queued",
            to_json(inputs),
            to_json({}),
            "",
            to_json({}),
            None,
            None,
            None,
            None,
            None,
            None,
            now_iso(),
            None,
            None,
        ),
    )


def _append_event(backend: SQLiteBackend):
    return lambda *a, **kw: agent_invoker.append_event(backend, *a, **kw)


class _RecordingGateway:
    """Duck-typed gateway that records each ``call`` and delegates to a real one."""

    def __init__(self, inner: InferenceGateway) -> None:
        self._inner = inner
        self.calls: list[tuple[ModelRequest, RunScope, RoutingPolicy | None]] = []

    def call(self, request, scope, *, policy=None, provider_call=None):
        self.calls.append((request, scope, policy))
        return self._inner.call(
            request, scope, policy=policy, provider_call=provider_call
        )


def _explosive_default_call(provider_id, request, scope, **_kwargs) -> ModelResponse:
    """A default provider_call that must never run: the override is always used."""
    raise AssertionError(
        "the gateway's default provider_call ran; the per-invocation override "
        "(the real DSPy execution) should have been used instead"
    )


def _make_gateway(events: EventRouter) -> InferenceGateway:
    return InferenceGateway(
        ProviderRouter(),
        events,
        provider_call=_explosive_default_call,
        sleep=lambda _s: None,
    )


# ---------------------------------------------------------------------------
# Gateway-routed invocation (Req 6.1, 5.4)
# ---------------------------------------------------------------------------


def test_invocation_routes_through_gateway_and_records_output(
    backend: SQLiteBackend,
    providers: ProviderService,
    provider: dict[str, Any],
    agent: dict[str, Any],
    stub_model_execution: list[str],
):
    """A configured gateway wraps the real model call via gateway.call (Req 6.1)."""
    invocation_id = "inv-gateway-1"
    inputs = {"prompt": "hello there"}
    _insert_invocation(backend, invocation_id, agent, provider, inputs)

    events = EventRouter(backend)
    gateway = _RecordingGateway(_make_gateway(events))

    execute_invocation(
        invocation_id,
        agent,
        provider,
        inputs,
        {},
        providers=providers,
        state=backend,
        append_event=_append_event(backend),
        gateway=gateway,
    )

    # The model call went through gateway.call exactly once, scoped to the agent
    # and routed at the agent's configured provider (Req 6.1).
    assert len(gateway.calls) == 1
    _request, scope, policy = gateway.calls[0]
    assert scope.definition_id == agent["id"]
    assert policy is not None and policy.fallback_order == [provider["id"]]

    # The real provider call (build_lm) was reached via the gateway pipeline, at
    # the routed provider id: no orphaned direct provider call.
    assert stub_model_execution == [provider["id"]]

    # Invocation + usage recording continues unchanged (Req 5.4).
    row = backend.fetch_one(
        "SELECT * FROM invocations WHERE id = ?", (invocation_id,)
    )
    assert row is not None
    assert row["status"] == "succeeded"
    assert row["output_text"] == "echoed: hello"
    assert row["reasoning_text"] == "stub reasoning"
    assert row["usage_json"] is not None
    assert row["error_message"] is None

    usage_row = backend.fetch_one(
        "SELECT total_tokens FROM usage_logs WHERE invocation_id = ?",
        (invocation_id,),
    )
    assert usage_row is not None and int(usage_row["total_tokens"]) == 8


def test_direct_path_when_no_gateway_is_configured(
    backend: SQLiteBackend,
    providers: ProviderService,
    provider: dict[str, Any],
    agent: dict[str, Any],
    stub_model_execution: list[str],
):
    """Without a gateway the invocation runs the DSPy program directly (back-compat)."""
    invocation_id = "inv-direct-1"
    inputs = {"prompt": "no gateway here"}
    _insert_invocation(backend, invocation_id, agent, provider, inputs)

    execute_invocation(
        invocation_id,
        agent,
        provider,
        inputs,
        {},
        providers=providers,
        state=backend,
        append_event=_append_event(backend),
        gateway=None,
    )

    assert stub_model_execution == [provider["id"]]

    row = backend.fetch_one(
        "SELECT * FROM invocations WHERE id = ?", (invocation_id,)
    )
    assert row is not None
    assert row["status"] == "succeeded"
    assert row["output_text"] == "echoed: hello"
    assert row["error_message"] is None


def test_orchestrator_passes_gateway_into_invocation(
    backend: SQLiteBackend,
    providers: ProviderService,
    provider: dict[str, Any],
    agent: dict[str, Any],
):
    """AgentOrchestrator forwards its gateway so invoke_agent routes through it."""
    events = EventRouter(backend)
    gateway = _RecordingGateway(_make_gateway(events))
    orchestrator = AgentOrchestrator(backend, providers, gateway=gateway)

    result = orchestrator.invoke_agent(agent["id"], {"inputs": {"prompt": "hi"}})
    invocation_id = result["id"]

    # The invocation runs in a background thread; wait for it to finish.
    deadline = time.time() + 10.0
    status = result["status"]
    while time.time() < deadline:
        row = backend.fetch_one(
            "SELECT status FROM invocations WHERE id = ?", (invocation_id,)
        )
        status = row["status"] if row else status
        if status in {"succeeded", "failed"}:
            break
        time.sleep(0.05)

    assert status == "succeeded"
    assert len(gateway.calls) == 1
