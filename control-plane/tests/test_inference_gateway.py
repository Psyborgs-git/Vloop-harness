"""Unit tests for the Inference_Gateway call pipeline (task 15.1).

Covers routing (Req 6.1), bounded-inclusive exponential-backoff retry (Req 6.2),
ordered fallback (Req 6.3), and exhaustion error + run-history recording
(Req 6.4). The provider call and the backoff clock are injected so retries are
exercised without real waiting.

Property tests for bounded retry (15.2) and ordered fallback/exhaustion (15.3)
live in their own files.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.database import SQLiteBackend
from core.event_router import EventRouter
from core.inference_gateway import (
    INFERENCE_EXHAUSTED_EVENT,
    InferenceGateway,
    ModelResponse,
    NonRetryableProviderError,
    ProviderExhaustionError,
    RetryableProviderError,
)
from core.orchestration_types import ModelRequest, RoutingPolicy, RunScope
from core.provider_router import ProviderHealth, ProviderMetrics, ProviderRouter


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def backend(tmp_path: Path) -> SQLiteBackend:
    return SQLiteBackend(tmp_path / "gateway-test.db")


@pytest.fixture()
def events(backend: SQLiteBackend) -> EventRouter:
    return EventRouter(backend)


def _request() -> ModelRequest:
    return ModelRequest(messages=[{"role": "user", "content": "hi"}])


def _scope(run_id: str = "run-1") -> RunScope:
    return RunScope(run_id=run_id, definition_id="def-1")


class _RecordingClock:
    """Captures backoff sleep durations instead of waiting."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


class _ScriptedProvider:
    """A provider_call driven by a per-provider script of outcomes.

    Each provider id maps to a list of outcomes consumed one per attempt. An
    outcome is either a :class:`ModelResponse` (success) or an ``Exception``
    instance (raised). Records the sequence of provider ids it was called with.
    """

    def __init__(self, scripts: dict[str, list[object]]) -> None:
        self._scripts = {pid: list(outcomes) for pid, outcomes in scripts.items()}
        self.calls: list[str] = []

    def __call__(self, provider_id, request, scope) -> ModelResponse:
        self.calls.append(provider_id)
        outcomes = self._scripts.get(provider_id, [])
        if not outcomes:
            raise RetryableProviderError("no scripted outcome", provider_id=provider_id)
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def attempts_for(self, provider_id: str) -> int:
        return self.calls.count(provider_id)


def _gateway(events, provider_call, *, sleep=None, default_policy=None, health_provider=None):
    return InferenceGateway(
        ProviderRouter(),
        events,
        provider_call=provider_call,
        default_policy=default_policy,
        health_provider=health_provider,
        sleep=sleep or (lambda _s: None),
        base_backoff_seconds=0.5,
        max_backoff_seconds=30.0,
    )


# ---------------------------------------------------------------------------
# Routing (Req 6.1)
# ---------------------------------------------------------------------------


def test_call_routes_to_first_candidate_and_returns_response(events):
    provider = _ScriptedProvider({"a": [ModelResponse(text="ok", provider_id="a")]})
    policy = RoutingPolicy(preference="cost", fallback_order=["a", "b"])
    gateway = _gateway(events, provider, default_policy=policy)

    response = gateway.call(_request(), _scope())

    assert response.text == "ok"
    assert response.provider_id == "a"
    assert provider.calls == ["a"]


def test_call_honors_per_call_policy_override(events):
    provider = _ScriptedProvider({"b": [ModelResponse(text="ok", provider_id="b")]})
    base = RoutingPolicy(fallback_order=["a"])
    override = RoutingPolicy(fallback_order=["b"])
    gateway = _gateway(events, provider, default_policy=base)

    response = gateway.call(_request(), _scope(), policy=override)

    assert response.provider_id == "b"
    assert provider.calls == ["b"]


def test_routing_excludes_unavailable_providers(events):
    provider = _ScriptedProvider({"b": [ModelResponse(text="ok", provider_id="b")]})
    policy = RoutingPolicy(fallback_order=["a", "b"])

    def health() -> ProviderHealth:
        return ProviderHealth(providers={"a": ProviderMetrics(available=False)})

    gateway = _gateway(events, provider, default_policy=policy, health_provider=health)

    response = gateway.call(_request(), _scope())

    # `a` is unavailable, so the gateway never attempts it.
    assert provider.calls == ["b"]
    assert response.provider_id == "b"


def test_response_provider_id_stamped_when_missing(events):
    provider = _ScriptedProvider({"a": [ModelResponse(text="ok", provider_id="")]})
    policy = RoutingPolicy(fallback_order=["a"])
    gateway = _gateway(events, provider, default_policy=policy)

    response = gateway.call(_request(), _scope())

    assert response.provider_id == "a"


# ---------------------------------------------------------------------------
# Bounded inclusive retry (Req 6.2)
# ---------------------------------------------------------------------------


def test_retry_succeeds_within_budget(events):
    # Fails twice (retryable) then succeeds on the third attempt; max_retries=3.
    provider = _ScriptedProvider(
        {
            "a": [
                RetryableProviderError("transient", provider_id="a"),
                RetryableProviderError("transient", provider_id="a"),
                ModelResponse(text="ok", provider_id="a"),
            ]
        }
    )
    clock = _RecordingClock()
    policy = RoutingPolicy(fallback_order=["a"], max_retries=3)
    gateway = _gateway(events, provider, sleep=clock, default_policy=policy)

    response = gateway.call(_request(), _scope())

    assert response.text == "ok"
    # 1 initial + 2 retries = 3 attempts.
    assert provider.attempts_for("a") == 3
    # Backoff slept before each retry: 0.5 * 2^0, 0.5 * 2^1.
    assert clock.delays == [0.5, 1.0]


def test_retry_is_bounded_and_inclusive_of_max(events):
    # Provider always fails; max_retries=2 -> exactly 3 attempts (1 + 2 retries).
    provider = _ScriptedProvider(
        {"a": [RetryableProviderError("transient", provider_id="a") for _ in range(10)]}
    )
    clock = _RecordingClock()
    policy = RoutingPolicy(fallback_order=["a"], max_retries=2)
    gateway = _gateway(events, provider, sleep=clock, default_policy=policy)

    with pytest.raises(ProviderExhaustionError):
        gateway.call(_request(), _scope())

    assert provider.attempts_for("a") == 3  # min(K+1, N+1) = min(11, 3)
    # Backoff slept before the 2 retries only, never after the final attempt.
    assert clock.delays == [0.5, 1.0]


def test_zero_max_retries_makes_single_attempt(events):
    provider = _ScriptedProvider(
        {"a": [RetryableProviderError("transient", provider_id="a")]}
    )
    clock = _RecordingClock()
    policy = RoutingPolicy(fallback_order=["a"], max_retries=0)
    gateway = _gateway(events, provider, sleep=clock, default_policy=policy)

    with pytest.raises(ProviderExhaustionError):
        gateway.call(_request(), _scope())

    assert provider.attempts_for("a") == 1
    assert clock.delays == []  # no retries -> no backoff


def test_non_retryable_error_skips_remaining_retries(events):
    # Non-retryable on the first attempt -> no retry even though budget allows it.
    provider = _ScriptedProvider(
        {
            "a": [NonRetryableProviderError("bad request", provider_id="a")],
            "b": [ModelResponse(text="ok", provider_id="b")],
        }
    )
    clock = _RecordingClock()
    policy = RoutingPolicy(fallback_order=["a", "b"], max_retries=5)
    gateway = _gateway(events, provider, sleep=clock, default_policy=policy)

    response = gateway.call(_request(), _scope())

    assert response.provider_id == "b"
    assert provider.attempts_for("a") == 1  # no retries on a
    assert clock.delays == []  # advanced straight to fallback


def test_generic_exception_is_treated_as_retryable(events):
    provider = _ScriptedProvider(
        {
            "a": [
                ValueError("unexpected transport blip"),
                ModelResponse(text="ok", provider_id="a"),
            ]
        }
    )
    clock = _RecordingClock()
    policy = RoutingPolicy(fallback_order=["a"], max_retries=2)
    gateway = _gateway(events, provider, sleep=clock, default_policy=policy)

    response = gateway.call(_request(), _scope())

    assert response.text == "ok"
    assert provider.attempts_for("a") == 2


def test_backoff_is_capped_at_max(events):
    provider = _ScriptedProvider(
        {"a": [RetryableProviderError("t", provider_id="a") for _ in range(6)]}
    )
    clock = _RecordingClock()
    policy = RoutingPolicy(fallback_order=["a"], max_retries=5)
    gateway = InferenceGateway(
        ProviderRouter(),
        events,
        provider_call=provider,
        default_policy=policy,
        sleep=clock,
        base_backoff_seconds=1.0,
        max_backoff_seconds=4.0,
    )

    with pytest.raises(ProviderExhaustionError):
        gateway.call(_request(), _scope())

    # 1, 2, 4, then capped at 4, 4 for the 5 retries.
    assert clock.delays == [1.0, 2.0, 4.0, 4.0, 4.0]


# ---------------------------------------------------------------------------
# Fallback order (Req 6.3)
# ---------------------------------------------------------------------------


def test_fallback_advances_in_order_on_exhaustion(events):
    provider = _ScriptedProvider(
        {
            "a": [RetryableProviderError("down", provider_id="a")],
            "b": [RetryableProviderError("down", provider_id="b")],
            "c": [ModelResponse(text="ok", provider_id="c")],
        }
    )
    policy = RoutingPolicy(fallback_order=["a", "b", "c"], max_retries=0)
    gateway = _gateway(events, provider, default_policy=policy)

    response = gateway.call(_request(), _scope())

    assert response.provider_id == "c"
    assert provider.calls == ["a", "b", "c"]


def test_fallback_retries_each_provider_before_advancing(events):
    provider = _ScriptedProvider(
        {
            "a": [RetryableProviderError("down", provider_id="a") for _ in range(3)],
            "b": [ModelResponse(text="ok", provider_id="b")],
        }
    )
    policy = RoutingPolicy(fallback_order=["a", "b"], max_retries=2)
    gateway = _gateway(events, provider, default_policy=policy)

    response = gateway.call(_request(), _scope())

    assert response.provider_id == "b"
    assert provider.attempts_for("a") == 3  # exhausted its retry budget first
    assert provider.attempts_for("b") == 1


# ---------------------------------------------------------------------------
# Exhaustion (Req 6.4)
# ---------------------------------------------------------------------------


def test_exhaustion_names_all_failed_providers(events):
    provider = _ScriptedProvider(
        {
            "a": [RetryableProviderError("down a", provider_id="a")],
            "b": [RetryableProviderError("down b", provider_id="b")],
        }
    )
    policy = RoutingPolicy(fallback_order=["a", "b"], max_retries=0)
    gateway = _gateway(events, provider, default_policy=policy)

    with pytest.raises(ProviderExhaustionError) as exc_info:
        gateway.call(_request(), _scope())

    error = exc_info.value
    assert error.failed_providers == ["a", "b"]
    assert "a" in str(error) and "b" in str(error)


def test_exhaustion_records_failure_in_run_history(events, backend: SQLiteBackend):
    provider = _ScriptedProvider(
        {
            "a": [RetryableProviderError("down a", provider_id="a")],
            "b": [RetryableProviderError("down b", provider_id="b")],
        }
    )
    policy = RoutingPolicy(fallback_order=["a", "b"], max_retries=0)
    gateway = _gateway(events, provider, default_policy=policy)

    with pytest.raises(ProviderExhaustionError):
        gateway.call(_request(), _scope("run-42"))

    history = events.history("run-42")
    assert len(history) == 1
    event = history[0]
    assert event.type == INFERENCE_EXHAUSTED_EVENT
    assert event.run_id == "run-42"
    assert event.payload["failed_providers"] == ["a", "b"]
    assert {f["provider_id"] for f in event.payload["failures"]} == {"a", "b"}


def test_no_candidates_records_exhaustion_with_empty_failures(events):
    provider = _ScriptedProvider({})
    # Empty fallback order and empty health -> the router returns no candidates.
    policy = RoutingPolicy(fallback_order=[], max_retries=0)
    gateway = _gateway(events, provider, default_policy=policy)

    with pytest.raises(ProviderExhaustionError) as exc_info:
        gateway.call(_request(), _scope("run-empty"))

    assert exc_info.value.failed_providers == []
    assert provider.calls == []
    history = events.history("run-empty")
    assert len(history) == 1
    assert history[0].type == INFERENCE_EXHAUSTED_EVENT


# ---------------------------------------------------------------------------
# Construction guards
# ---------------------------------------------------------------------------


def test_constructor_requires_collaborators(events):
    with pytest.raises(ValueError):
        InferenceGateway(None, events, provider_call=lambda *_: None)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        InferenceGateway(ProviderRouter(), None, provider_call=lambda *_: None)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        InferenceGateway(ProviderRouter(), events, provider_call=None)  # type: ignore[arg-type]
