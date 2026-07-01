"""Unit tests for core.provider_router policy selection and fallback ordering."""

from __future__ import annotations

from core.orchestration_types import RoutingPolicy
from core.provider_router import ProviderHealth, ProviderMetrics, ProviderRouter


def _health(**providers: ProviderMetrics) -> ProviderHealth:
    return ProviderHealth(providers=dict(providers))


def test_no_metrics_returns_configured_fallback_order():
    # With no metric data the result is exactly the configured fallback order.
    router = ProviderRouter()
    policy = RoutingPolicy(preference="cost", fallback_order=["a", "b", "c"])
    assert router.select(policy, ProviderHealth()) == ["a", "b", "c"]


def test_cost_preference_orders_cheapest_first():
    router = ProviderRouter()
    policy = RoutingPolicy(preference="cost", fallback_order=["a", "b", "c"])
    health = _health(
        a=ProviderMetrics(cost_per_token=0.30),
        b=ProviderMetrics(cost_per_token=0.10),
        c=ProviderMetrics(cost_per_token=0.20),
    )
    assert router.select(policy, health) == ["b", "c", "a"]


def test_speed_preference_orders_fastest_first():
    router = ProviderRouter()
    policy = RoutingPolicy(preference="speed", fallback_order=["a", "b", "c"])
    health = _health(
        a=ProviderMetrics(latency_ms=300.0),
        b=ProviderMetrics(latency_ms=100.0),
        c=ProviderMetrics(latency_ms=200.0),
    )
    assert router.select(policy, health) == ["b", "c", "a"]


def test_quality_preference_orders_best_score_first():
    router = ProviderRouter()
    policy = RoutingPolicy(preference="quality", fallback_order=["a", "b", "c"])
    health = _health(
        a=ProviderMetrics(quality_score=0.5),
        b=ProviderMetrics(quality_score=0.9),
        c=ProviderMetrics(quality_score=0.7),
    )
    assert router.select(policy, health) == ["b", "c", "a"]


def test_unavailable_providers_are_excluded():
    router = ProviderRouter()
    policy = RoutingPolicy(preference="cost", fallback_order=["a", "b", "c"])
    health = _health(
        a=ProviderMetrics(cost_per_token=0.10, available=False),
        b=ProviderMetrics(cost_per_token=0.20),
        c=ProviderMetrics(cost_per_token=0.30),
    )
    # `a` is cheapest but unavailable, so it is dropped entirely.
    assert router.select(policy, health) == ["b", "c"]


def test_ties_break_on_configured_fallback_order():
    router = ProviderRouter()
    policy = RoutingPolicy(preference="cost", fallback_order=["a", "b", "c"])
    health = _health(
        a=ProviderMetrics(cost_per_token=0.10),
        b=ProviderMetrics(cost_per_token=0.10),
        c=ProviderMetrics(cost_per_token=0.10),
    )
    # Equal cost -> stable, configured order preserved.
    assert router.select(policy, health) == ["a", "b", "c"]


def test_empty_fallback_order_uses_health_providers():
    router = ProviderRouter()
    policy = RoutingPolicy(preference="cost", fallback_order=[])
    health = _health(
        a=ProviderMetrics(cost_per_token=0.30),
        b=ProviderMetrics(cost_per_token=0.10),
    )
    assert router.select(policy, health) == ["b", "a"]


def test_unknown_preference_falls_back_to_configured_order():
    router = ProviderRouter()
    policy = RoutingPolicy(preference="bogus", fallback_order=["a", "b", "c"])
    health = _health(
        a=ProviderMetrics(cost_per_token=0.30),
        b=ProviderMetrics(cost_per_token=0.10),
        c=ProviderMetrics(cost_per_token=0.20),
    )
    assert router.select(policy, health) == ["a", "b", "c"]


def test_duplicate_fallback_entries_are_deduplicated():
    router = ProviderRouter()
    policy = RoutingPolicy(preference="cost", fallback_order=["a", "b", "a", "c"])
    assert router.select(policy, ProviderHealth()) == ["a", "b", "c"]


def test_unknown_provider_treated_as_available_with_neutral_metrics():
    router = ProviderRouter()
    policy = RoutingPolicy(preference="cost", fallback_order=["a", "b"])
    # Only `a` has metrics; `b` is unknown -> neutral (cost 0.0), available.
    health = _health(a=ProviderMetrics(cost_per_token=0.50))
    assert router.select(policy, health) == ["b", "a"]


def test_provider_health_helpers():
    health = _health(a=ProviderMetrics(available=False, cost_per_token=0.2))
    assert health.is_available("a") is False
    assert health.is_available("unknown") is True
    assert health.metrics_for("a").cost_per_token == 0.2
    assert health.metrics_for("unknown") == ProviderMetrics()
    assert health.to_dict()["a"]["available"] is False
