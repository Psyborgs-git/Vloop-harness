"""Property-based test for Inference_Gateway bounded, inclusive retry.

# Feature: orchestration-engine-completion, Property 17: Retry is bounded and inclusive of the configured maximum

Property 17 states that for any configured maximum retry count ``N`` and a
single provider that returns retryable errors ``K`` times before succeeding (or
always fails), the Inference_Gateway attempts that provider *exactly*
``min(K + 1, N + 1)`` times: one initial attempt plus up to ``N`` retries, never
more than ``N`` retries. Backoff between retries is exercised through an injected
no-op sleep so the property runs without real waiting.

* If the provider succeeds on its ``(K + 1)``-th attempt and ``K <= N`` (so the
  success lands within the retry budget), the call succeeds after exactly
  ``K + 1`` attempts.
* Otherwise (the provider always fails, or ``K > N`` so the budget runs out
  before the success), the provider is attempted exactly ``N + 1`` times and the
  call raises :class:`ProviderExhaustionError`.

**Validates: Requirements 6.2**
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.database import SQLiteBackend
from core.event_router import EventRouter
from core.inference_gateway import (
    InferenceGateway,
    ModelResponse,
    ProviderExhaustionError,
    RetryableProviderError,
)
from core.orchestration_types import ModelRequest, RoutingPolicy, RunScope
from core.provider_router import ProviderRouter

# ---------------------------------------------------------------------------
# Shared temp SQLite-backed EventRouter
# ---------------------------------------------------------------------------

# A single temp SQLite backend is created once and reused across all generated
# examples. The gateway only writes to it on the exhaustion path; reusing it
# keeps the property fast while still exercising the real EventRouter wiring.
_TMP_DIR = tempfile.mkdtemp(prefix="vloop-bounded-retry-")
_BACKEND = SQLiteBackend(Path(_TMP_DIR) / "events.db")
_EVENTS = EventRouter(_BACKEND)

_PROVIDER_ID = "p"


class _CountingProvider:
    """A single-provider ``provider_call`` script that counts attempts.

    The provider fails with a retryable error for the first ``fail_times``
    attempts. If ``always_fail`` is set it keeps failing forever; otherwise the
    next attempt returns a successful :class:`ModelResponse`.
    """

    def __init__(self, *, fail_times: int, always_fail: bool) -> None:
        self._fail_times = fail_times
        self._always_fail = always_fail
        self.attempts = 0

    def __call__(self, provider_id, request, scope) -> ModelResponse:
        self.attempts += 1
        if self._always_fail or self.attempts <= self._fail_times:
            raise RetryableProviderError("transient", provider_id=provider_id)
        return ModelResponse(text="ok", provider_id=provider_id)


def _gateway(provider: _CountingProvider, max_retries: int) -> InferenceGateway:
    return InferenceGateway(
        ProviderRouter(),
        _EVENTS,
        provider_call=provider,
        default_policy=RoutingPolicy(fallback_order=[_PROVIDER_ID], max_retries=max_retries),
        sleep=lambda _s: None,  # injected no-op sleep: no real backoff waiting
        base_backoff_seconds=0.5,
        max_backoff_seconds=30.0,
    )


# ---------------------------------------------------------------------------
# Property 17: Retry is bounded and inclusive of the configured maximum
# ---------------------------------------------------------------------------


@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
@given(
    # N = configured maximum retry count.
    max_retries=st.integers(min_value=0, max_value=12),
    # K = number of consecutive retryable failures before a success.
    fail_times=st.integers(min_value=0, max_value=15),
    # When True the provider never succeeds (K is effectively unbounded).
    always_fail=st.booleans(),
)
def test_retry_is_bounded_and_inclusive_of_max(
    max_retries: int, fail_times: int, always_fail: bool
) -> None:
    provider = _CountingProvider(fail_times=fail_times, always_fail=always_fail)
    gateway = _gateway(provider, max_retries)

    if always_fail:
        # No success is ever reachable: the provider is attempted exactly the
        # full budget (1 initial + N retries) and then exhaustion is raised.
        expected_attempts = max_retries + 1
        with pytest.raises(ProviderExhaustionError):
            gateway.call(ModelRequest(messages=[{"role": "user", "content": "hi"}]),
                         RunScope(run_id="run-1", definition_id="def-1"))
    else:
        # Success arrives on attempt K + 1. The gateway reaches it only if that
        # attempt is within the inclusive budget of N + 1 attempts.
        expected_attempts = min(fail_times + 1, max_retries + 1)
        if fail_times <= max_retries:
            response = gateway.call(
                ModelRequest(messages=[{"role": "user", "content": "hi"}]),
                RunScope(run_id="run-1", definition_id="def-1"),
            )
            assert response.text == "ok"
            assert response.provider_id == _PROVIDER_ID
        else:
            with pytest.raises(ProviderExhaustionError):
                gateway.call(
                    ModelRequest(messages=[{"role": "user", "content": "hi"}]),
                    RunScope(run_id="run-1", definition_id="def-1"),
                )

    # The core property: attempts == min(K + 1, N + 1), never more than N retries.
    assert provider.attempts == expected_attempts
    assert provider.attempts <= max_retries + 1
