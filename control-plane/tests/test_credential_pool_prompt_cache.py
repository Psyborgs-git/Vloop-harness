"""Unit tests for CredentialPoolManager, PromptCache, and their gateway wiring.

Covers task 17.1:

* Credentials come only via kernel grants and the manager caches only the
  granted session context, never raw secrets (Req 6.5).
* Credential_Pool grants rotate across successive calls (Req 19.2).
* A grant the provider rejects as invalid is quarantined and another grant is
  selected, with the rejected grant retained for review (Req 19.3).
* A Prompt_Cache hit returns the cached response without a new provider call
  (Req 19.4).

Property tests for these behaviours live in their own files (tasks 17.2-17.4).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.database import SQLiteBackend
from core.event_router import EventRouter
from core.inference_gateway import (
    CredentialPoolManager,
    InferenceGateway,
    InvalidGrantError,
    ModelResponse,
    PromptCache,
)
from core.orchestration_types import (
    GrantContext,
    ModelRequest,
    RoutingPolicy,
    RunScope,
)
from core.provider_router import ProviderRouter


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def backend(tmp_path: Path) -> SQLiteBackend:
    return SQLiteBackend(tmp_path / "credpool-test.db")


@pytest.fixture()
def events(backend: SQLiteBackend) -> EventRouter:
    return EventRouter(backend)


def _request(cache_key: str = "") -> ModelRequest:
    return ModelRequest(messages=[{"role": "user", "content": "hi"}], cache_key=cache_key)


def _scope() -> RunScope:
    return RunScope(run_id="run-1", definition_id="def-1")


class _RecordingGrantSource:
    """A grant source that returns a GrantContext per secret ref (no raw secret)."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, str]] = []

    def __call__(self, secret_ref: str, target: str) -> GrantContext:
        self.requests.append((secret_ref, target))
        # Returns session context only; never a raw secret value (Req 6.5).
        return GrantContext(grant_id=f"grant::{secret_ref}", session_ref=f"sess::{secret_ref}")


# ---------------------------------------------------------------------------
# CredentialPoolManager (Req 6.5, 19.2, 19.3)
# ---------------------------------------------------------------------------


def test_constructor_requires_grant_source():
    with pytest.raises(ValueError):
        CredentialPoolManager(None)  # type: ignore[arg-type]


def test_acquire_returns_none_when_no_pool_configured():
    pools = CredentialPoolManager(_RecordingGrantSource())
    assert pools.has_pool("openai") is False
    assert pools.acquire("openai", target="t") is None


def test_acquire_obtains_grant_only_via_grant_source():
    source = _RecordingGrantSource()
    pools = CredentialPoolManager(source, pools={"openai": ["s1"]})

    grant = pools.acquire("openai", target="inference:openai")

    assert isinstance(grant, GrantContext)
    assert grant.grant_id == "grant::s1"
    assert grant.session_ref == "sess::s1"
    assert source.requests == [("s1", "inference:openai")]


def test_acquire_rotates_across_pool_grants_on_successive_calls():
    source = _RecordingGrantSource()
    pools = CredentialPoolManager(source, pools={"openai": ["s1", "s2", "s3"]})

    seen = [pools.acquire("openai", target="t").grant_id for _ in range(4)]

    # Round-robin across the three grants, wrapping back to the first.
    assert seen == ["grant::s1", "grant::s2", "grant::s3", "grant::s1"]


def test_grant_session_context_is_cached_not_re_requested():
    source = _RecordingGrantSource()
    pools = CredentialPoolManager(source, pools={"openai": ["s1"]})

    first = pools.acquire("openai", target="t")
    second = pools.acquire("openai", target="t")

    assert first.grant_id == second.grant_id == "grant::s1"
    # Cached session context is reused; the grant source is hit only once.
    assert source.requests == [("s1", "t")]


def test_quarantine_records_rejected_grant_and_skips_it():
    source = _RecordingGrantSource()
    pools = CredentialPoolManager(source, pools={"openai": ["s1", "s2"]})

    bad = pools.acquire("openai", target="t")
    assert bad.grant_id == "grant::s1"
    pools.quarantine("openai", bad, reason="401 invalid key")

    # Subsequent acquisitions never return the quarantined grant again.
    for _ in range(4):
        grant = pools.acquire("openai", target="t")
        assert grant.grant_id == "grant::s2"

    review = pools.quarantined
    assert len(review) == 1
    assert review[0].provider_id == "openai"
    assert review[0].secret_ref == "s1"
    assert review[0].reason == "401 invalid key"


def test_acquire_returns_none_when_all_grants_quarantined():
    source = _RecordingGrantSource()
    pools = CredentialPoolManager(source, pools={"openai": ["s1", "s2"]})

    pools.quarantine("openai", pools.acquire("openai", target="t"))
    pools.quarantine("openai", pools.acquire("openai", target="t"))

    assert pools.acquire("openai", target="t") is None


def test_grant_context_holds_no_raw_secret_value():
    source = _RecordingGrantSource()
    pools = CredentialPoolManager(source, pools={"openai": ["s1"]})

    grant = pools.acquire("openai", target="t")

    # GrantContext is a slotted dataclass exposing exactly grant id + session ref.
    assert set(GrantContext.__slots__) == {"grant_id", "session_ref"}
    assert not hasattr(grant, "secret")
    assert not hasattr(grant, "value")


# ---------------------------------------------------------------------------
# PromptCache (Req 19.4)
# ---------------------------------------------------------------------------


def test_prompt_cache_miss_then_hit():
    cache = PromptCache()
    request = _request(cache_key="k1")
    response = ModelResponse(text="cached", provider_id="a")

    assert cache.get(request) is None
    cache.put(request, response)
    assert cache.get(request) is response


def test_prompt_cache_ignores_requests_without_cache_key():
    cache = PromptCache()
    request = _request(cache_key="")
    cache.put(request, ModelResponse(text="x", provider_id="a"))
    assert cache.get(request) is None


def test_prompt_cache_disabled_never_serves():
    cache = PromptCache(enabled=False)
    request = _request(cache_key="k1")
    cache.put(request, ModelResponse(text="x", provider_id="a"))
    assert cache.get(request) is None


def test_prompt_cache_evicts_oldest_when_bounded():
    cache = PromptCache(max_entries=2)
    cache.put(_request("k1"), ModelResponse(text="1", provider_id="a"))
    cache.put(_request("k2"), ModelResponse(text="2", provider_id="a"))
    cache.put(_request("k3"), ModelResponse(text="3", provider_id="a"))

    assert cache.get(_request("k1")) is None  # evicted
    assert cache.get(_request("k2")).text == "2"
    assert cache.get(_request("k3")).text == "3"


# ---------------------------------------------------------------------------
# Gateway wiring (Req 19.2, 19.3, 19.4)
# ---------------------------------------------------------------------------


def _gateway(events, provider_call, *, cache=None, pools=None, policy=None):
    return InferenceGateway(
        ProviderRouter(),
        events,
        provider_call=provider_call,
        default_policy=policy or RoutingPolicy(fallback_order=["a"], max_retries=2),
        sleep=lambda _s: None,
        cache=cache,
        pools=pools,
    )


def test_cache_hit_short_circuits_provider_call(events):
    calls: list[str] = []

    def provider_call(pid, req, scope):
        calls.append(pid)
        return ModelResponse(text="fresh", provider_id=pid)

    cache = PromptCache()
    gateway = _gateway(events, provider_call, cache=cache)
    request = _request(cache_key="k1")

    first = gateway.call(request, _scope())
    assert first.text == "fresh"
    assert calls == ["a"]

    # Second identical request is served from cache: no new provider call.
    second = gateway.call(request, _scope())
    assert second.text == "fresh"
    assert calls == ["a"]


def test_gateway_rotates_pool_grants_across_calls(events):
    used_grants: list[str] = []

    def provider_call(pid, req, scope, *, grant):
        used_grants.append(grant.grant_id)
        return ModelResponse(text="ok", provider_id=pid)

    pools = CredentialPoolManager(
        _RecordingGrantSource(), pools={"a": ["s1", "s2"]}
    )
    gateway = _gateway(events, provider_call, pools=pools)

    for _ in range(3):
        gateway.call(_request(), _scope())

    assert used_grants == ["grant::s1", "grant::s2", "grant::s1"]


def test_gateway_quarantines_invalid_grant_and_selects_another(events):
    used_grants: list[str] = []

    def provider_call(pid, req, scope, *, grant):
        used_grants.append(grant.grant_id)
        if grant.grant_id == "grant::s1":
            raise InvalidGrantError("rejected", provider_id=pid)
        return ModelResponse(text="ok", provider_id=pid)

    pools = CredentialPoolManager(
        _RecordingGrantSource(), pools={"a": ["s1", "s2"]}
    )
    gateway = _gateway(events, provider_call, pools=pools)

    response = gateway.call(_request(), _scope())

    assert response.text == "ok"
    # First grant rejected then quarantined; second grant succeeds.
    assert used_grants == ["grant::s1", "grant::s2"]
    review = pools.quarantined
    assert len(review) == 1
    assert review[0].secret_ref == "s1"
