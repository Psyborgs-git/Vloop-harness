"""Property-based test for ordered provider fallback and exhaustion reporting.

# Feature: orchestration-engine-completion, Property 18: Fallback proceeds in order and reports exhaustion

Property 18 states that for any configured ordered list of providers
(``RoutingPolicy.fallback_order``) and any position of the first provider that
succeeds (or no success at all), the Inference_Gateway:

* attempts providers strictly in the configured order, up to and including the
  first provider that succeeds, and attempts no later provider once one
  succeeds (Requirement 6.3 — fallback proceeds to the next provider in order
  only while earlier providers are exhausted); and
* when every provider in the fallback order is exhausted, raises
  :class:`ProviderExhaustionError` naming exactly all configured providers in
  order and records an ``inference.exhausted`` event in the Workflow_Run event
  history (Requirement 6.4).

The provider call is scripted to record the order of provider ids it is asked
to call, and the backoff sleep is a no-op so retries/fallback are exercised
without real waiting. Event history is read back from a real temporary
SQLite-backed :class:`~core.event_router.EventRouter`.

**Validates: Requirements 6.3, 6.4**
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.database import SQLiteBackend
from core.event_router import EventRouter
from core.inference_gateway import (
    INFERENCE_EXHAUSTED_EVENT,
    InferenceGateway,
    ModelResponse,
    ProviderExhaustionError,
    RetryableProviderError,
)
from core.orchestration_types import ModelRequest, RoutingPolicy, RunScope
from core.provider_router import ProviderRouter

# ---------------------------------------------------------------------------
# Scripted provider
# ---------------------------------------------------------------------------


class _OrderRecordingProvider:
    """A ``provider_call`` that records every provider id it is asked to call.

    Failing providers raise a retryable error on every attempt; the single
    designated ``success_provider`` (when any) returns a :class:`ModelResponse`.
    Recording the call order lets the test assert the gateway walks the
    configured fallback order and stops at the first success.
    """

    def __init__(self, success_provider: str | None) -> None:
        self._success_provider = success_provider
        self.calls: list[str] = []

    def __call__(self, provider_id, request, scope) -> ModelResponse:
        self.calls.append(provider_id)
        if provider_id == self._success_provider:
            return ModelResponse(text="ok", provider_id=provider_id)
        raise RetryableProviderError("provider down", provider_id=provider_id)

    def distinct_call_order(self) -> list[str]:
        """The order distinct providers were first attempted in."""
        seen: set[str] = set()
        order: list[str] = []
        for provider_id in self.calls:
            if provider_id not in seen:
                seen.add(provider_id)
                order.append(provider_id)
        return order


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


@st.composite
def _fallback_scenarios(draw: st.DrawFn) -> dict:
    """Generate a unique ordered provider list and a first-success position.

    ``success_index`` is an index into ``fallback_order`` selecting the first
    provider that succeeds, or ``len(fallback_order)`` meaning no provider
    succeeds (every provider is exhausted). ``max_retries`` varies so each
    provider may be attempted more than once before the fallback advances.
    """
    fallback_order = draw(
        st.lists(
            st.text(
                alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
                min_size=1,
                max_size=6,
            ),
            min_size=1,
            max_size=6,
            unique=True,
        )
    )
    # 0..len-1 -> that provider is the first success; len -> all fail.
    success_index = draw(st.integers(min_value=0, max_value=len(fallback_order)))
    max_retries = draw(st.integers(min_value=0, max_value=3))
    return {
        "fallback_order": fallback_order,
        "success_index": success_index,
        "max_retries": max_retries,
    }


# ---------------------------------------------------------------------------
# Property 18: Fallback proceeds in order and reports exhaustion
# ---------------------------------------------------------------------------


# deadline=None: each example does real (temp) SQLite I/O whose timing varies;
# the property is about ordering and exhaustion reporting, not latency.
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(scenario=_fallback_scenarios())
def test_fallback_proceeds_in_order_and_reports_exhaustion(
    scenario: dict, tmp_path_factory
) -> None:
    fallback_order: list[str] = scenario["fallback_order"]
    success_index: int = scenario["success_index"]
    max_retries: int = scenario["max_retries"]
    all_fail = success_index == len(fallback_order)
    success_provider = None if all_fail else fallback_order[success_index]

    # Fresh, isolated temp SQLite-backed EventRouter per example.
    db_dir: Path = tmp_path_factory.mktemp("fallback-exhaustion")
    backend = SQLiteBackend(db_dir / f"gateway-{uuid.uuid4().hex}.db")
    events = EventRouter(backend)
    run_id = f"run-{uuid.uuid4().hex}"

    provider = _OrderRecordingProvider(success_provider)
    policy = RoutingPolicy(fallback_order=fallback_order, max_retries=max_retries)
    gateway = InferenceGateway(
        ProviderRouter(),
        events,
        provider_call=provider,
        default_policy=policy,
        sleep=lambda _seconds: None,  # no-op backoff
        base_backoff_seconds=0.0,
        max_backoff_seconds=0.0,
    )
    request = ModelRequest(messages=[{"role": "user", "content": "hi"}])
    scope = RunScope(run_id=run_id, definition_id="def-1")

    if not all_fail:
        # --- First success short-circuits the fallback order ----------------
        response = gateway.call(request, scope)

        # The serving provider is exactly the designated first success.
        assert response.provider_id == success_provider

        # Providers were attempted strictly in configured order, up to and
        # including the first success, with no later provider attempted.
        expected_prefix = fallback_order[: success_index + 1]
        assert provider.distinct_call_order() == expected_prefix
        # No provider after the success is ever attempted.
        later = set(fallback_order[success_index + 1 :])
        assert later.isdisjoint(provider.calls)

        # Each provider before the success was retried up to and including the
        # bound (1 initial + max_retries), and the success provider once.
        for failed in fallback_order[:success_index]:
            assert provider.calls.count(failed) == max_retries + 1
        assert provider.calls.count(success_provider) == 1

        # A successful call records no exhaustion event.
        exhausted_events = [
            e for e in events.history(run_id) if e.type == INFERENCE_EXHAUSTED_EVENT
        ]
        assert exhausted_events == []
    else:
        # --- Exhaustion names every provider in order and is recorded -------
        with pytest.raises(ProviderExhaustionError) as exc_info:
            gateway.call(request, scope)

        error = exc_info.value
        # The error names exactly all configured providers, in order.
        assert error.failed_providers == fallback_order
        for provider_id in fallback_order:
            assert provider_id in str(error)

        # Every provider was attempted, strictly in configured order.
        assert provider.distinct_call_order() == fallback_order

        # An exhaustion event is recorded in the run history naming all
        # providers in order.
        history = events.history(run_id)
        exhausted_events = [
            e for e in history if e.type == INFERENCE_EXHAUSTED_EVENT
        ]
        assert len(exhausted_events) == 1
        event = exhausted_events[0]
        assert event.run_id == run_id
        assert event.payload["failed_providers"] == fallback_order
