"""Property-based test for Prompt_Cache hits avoiding provider calls.

# Feature: orchestration-engine-completion, Property 43: Prompt cache hits avoid provider calls

Property 43 states that *for any* sequence of model requests routed through an
:class:`~core.inference_gateway.InferenceGateway` configured with a
:class:`~core.inference_gateway.PromptCache`:

* The **first** request carrying a given non-empty ``cache_key`` triggers a
  provider call and the response is stored in the cache.
* Every **subsequent** request with the *same* non-empty ``cache_key`` is served
  from the cache and issues **no** additional provider call, returning exactly
  the originally cached response (Req 19.4).
* Requests with an **empty** ``cache_key`` are never cached and therefore
  **always** invoke the provider.

The test generates random sequences of requests whose cache keys are drawn from
a small pool (so non-empty keys repeat) plus the empty key, routes them through
a gateway whose ``provider_call`` counts its invocations and returns a unique
response per call, and asserts the exact provider-call count and per-request
return values predicted by the model above.

**Validates: Requirements 19.4**
"""

from __future__ import annotations

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from core.database import SQLiteBackend
from core.event_router import EventRouter
from core.inference_gateway import (
    InferenceGateway,
    ModelResponse,
    PromptCache,
)
from core.orchestration_types import (
    ModelRequest,
    RoutingPolicy,
    RunScope,
)
from core.provider_router import ProviderRouter

# ---------------------------------------------------------------------------
# Strategies: random sequences of cache keys (some repeated, some empty)
# ---------------------------------------------------------------------------

# A small pool of non-empty keys plus the empty key. Drawing from a small pool
# guarantees repeats are common, so the "subsequent hit" branch is exercised,
# while the empty key exercises the never-cached branch.
_CACHE_KEYS = st.sampled_from(["", "k1", "k2", "k3", "k4"])

_KEY_SEQUENCES = st.lists(_CACHE_KEYS, min_size=1, max_size=40)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _CountingProvider:
    """A provider_call that counts invocations and returns a unique response.

    Each invocation yields a distinct response text so a cache hit (which must
    return the *originally stored* response) is distinguishable from a fresh
    provider call.
    """

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, provider_id: str, request: ModelRequest, scope: RunScope) -> ModelResponse:
        self.calls += 1
        return ModelResponse(text=f"resp-{self.calls}", provider_id=provider_id)


def _request(cache_key: str) -> ModelRequest:
    return ModelRequest(
        messages=[{"role": "user", "content": "hi"}], cache_key=cache_key
    )


# ---------------------------------------------------------------------------
# Property 43
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(keys=_KEY_SEQUENCES)
def test_prompt_cache_hits_avoid_provider_calls(tmp_path_factory, keys: list[str]) -> None:
    # Temp SQLite-backed EventRouter (events are emitted but irrelevant to the
    # property; the router only needs somewhere to persist them).
    db_path: Path = tmp_path_factory.mktemp("prompt-cache") / "events.db"
    backend = SQLiteBackend(db_path)
    events = EventRouter(backend)

    provider = _CountingProvider()
    cache = PromptCache()
    gateway = InferenceGateway(
        ProviderRouter(),
        events,
        provider_call=provider,
        default_policy=RoutingPolicy(fallback_order=["a"], max_retries=0),
        sleep=lambda _s: None,
        cache=cache,
    )
    scope = RunScope(run_id="run-1", definition_id="def-1")

    # Model the expected behaviour independently of the gateway.
    cached_text: dict[str, str] = {}
    expected_calls = 0

    for key in keys:
        response = gateway.call(_request(key), scope)

        if key == "":
            # Empty cache key: always a fresh provider call, never cached.
            expected_calls += 1
            assert response.text == f"resp-{expected_calls}"
            assert cache.get(_request("")) is None
        elif key in cached_text:
            # Subsequent request for a known key: served from cache, NO new
            # provider call (Req 19.4), returning the originally cached response.
            assert response.text == cached_text[key]
        else:
            # First request for a non-empty key: provider call, then cached.
            expected_calls += 1
            assert response.text == f"resp-{expected_calls}"
            cached_text[key] = response.text

        # The provider was invoked exactly the predicted number of times.
        assert provider.calls == expected_calls
