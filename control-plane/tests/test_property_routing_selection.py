"""Property-based test for Provider_Router policy/preference selection.

# Feature: orchestration-engine-completion, Property 16: Routing selects per policy and preference

Property 16 states that for any routing policy whose optimization preference is
one of cost, speed, or quality, and any set of providers with arbitrary health
metrics, the Provider_Router selects an ordered candidate list that is
consistent with that policy and preference:

* unavailable providers are excluded (provider health is honored);
* the remaining candidates are ordered by the preference metric
  (cost ascending, speed = latency ascending, quality = score descending);
* providers that tie on the preference metric keep their relative position in
  the configured fallback order (stable tie-break).

**Validates: Requirements 6.1, 19.1**
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.orchestration_types import RoutingPolicy
from core.provider_router import ProviderHealth, ProviderMetrics, ProviderRouter

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# A small id pool so duplicates, ties, and configured/health overlap occur
# frequently across generated examples.
_PROVIDER_IDS = ["a", "b", "c", "d", "e", "f"]

_PREFERENCES = ["cost", "speed", "quality"]

# Discrete metric values keep the space small enough that ties between
# providers are common, which is what exercises the configured-order
# tie-breaker.
_metric_values = st.sampled_from([0.0, 0.1, 0.2, 0.3, 0.5, 1.0])


@st.composite
def _provider_metrics(draw: st.DrawFn) -> ProviderMetrics:
    return ProviderMetrics(
        available=draw(st.booleans()),
        cost_per_token=draw(_metric_values),
        latency_ms=draw(_metric_values),
        quality_score=draw(_metric_values),
    )


@st.composite
def _health(draw: st.DrawFn) -> ProviderHealth:
    ids = draw(st.lists(st.sampled_from(_PROVIDER_IDS), unique=True, max_size=6))
    return ProviderHealth(providers={pid: draw(_provider_metrics()) for pid in ids})


@st.composite
def _policy(draw: st.DrawFn) -> RoutingPolicy:
    # fallback_order may contain duplicates and ids absent from the health
    # snapshot; both are valid inputs the router must tolerate.
    fallback_order = draw(st.lists(st.sampled_from(_PROVIDER_IDS), max_size=8))
    preference = draw(st.sampled_from(_PREFERENCES))
    return RoutingPolicy(preference=preference, fallback_order=fallback_order)


# ---------------------------------------------------------------------------
# Helpers mirroring the router's input model (not its sorting logic)
# ---------------------------------------------------------------------------


def _deduped_universe(policy: RoutingPolicy, health: ProviderHealth) -> list[str]:
    """The candidate universe in configured order, duplicates removed.

    Mirrors the router's universe selection: the configured fallback order when
    present, otherwise every provider in the health snapshot.
    """
    source = policy.fallback_order if policy.fallback_order else list(health.providers)
    seen: set[str] = set()
    ordered: list[str] = []
    for pid in source:
        if pid not in seen:
            seen.add(pid)
            ordered.append(pid)
    return ordered


def _metric_for(preference: str, metrics: ProviderMetrics) -> float:
    """The comparable metric value for ``preference`` (smaller sorts earlier)."""
    if preference == "cost":
        return metrics.cost_per_token
    if preference == "speed":
        return metrics.latency_ms
    # quality: higher score is better, so negate to keep "smaller earlier".
    return -metrics.quality_score


# ---------------------------------------------------------------------------
# Property 16: Routing selects per policy and preference
# ---------------------------------------------------------------------------


@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
@given(policy=_policy(), health=_health())
def test_routing_selects_per_policy_and_preference(
    policy: RoutingPolicy, health: ProviderHealth
) -> None:
    router = ProviderRouter()
    result = router.select(policy, health)

    universe = _deduped_universe(policy, health)
    universe_pos = {pid: i for i, pid in enumerate(universe)}

    # --- Exclusion: result is exactly the available providers of the universe.
    expected_set = {pid for pid in universe if health.is_available(pid)}
    assert set(result) == expected_set
    # No unavailable provider survives.
    assert all(health.is_available(pid) for pid in result)
    # No duplicates introduced.
    assert len(result) == len(set(result))

    # --- Ordering: adjacent candidates are monotonic on the preference metric,
    # and providers that tie keep their configured-fallback-order position.
    pref = policy.preference
    for left, right in zip(result, result[1:]):
        left_key = _metric_for(pref, health.metrics_for(left))
        right_key = _metric_for(pref, health.metrics_for(right))
        assert left_key <= right_key
        if left_key == right_key:
            # Tie -> configured order decides (stable). The earlier-listed
            # provider in the deduped universe must come first.
            assert universe_pos[left] < universe_pos[right]
