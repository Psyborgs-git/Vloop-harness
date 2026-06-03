"""Tests for model registry and router."""

from __future__ import annotations

import pytest

from harness.engine.model_registry import ModelCapability, ModelInfo, ModelRegistry
from harness.engine.model_router import ModelRouter, RoutingStrategy


@pytest.fixture
def registry() -> ModelRegistry:
    return ModelRegistry()


@pytest.fixture
def router(registry: ModelRegistry) -> ModelRouter:
    return ModelRouter(registry=registry)


class TestModelRegistry:
    def test_static_catalog_loaded(self, registry: ModelRegistry) -> None:
        assert len(registry.list_all()) > 0

    def test_get_known_model(self, registry: ModelRegistry) -> None:
        info = registry.get("gpt-4o")
        assert info is not None
        assert info.provider_type == "openai"
        assert info.context_window == 128_000

    def test_list_by_provider(self, registry: ModelRegistry) -> None:
        anthropic = registry.list_by_provider("anthropic")
        assert len(anthropic) >= 3

    def test_list_by_capability(self, registry: ModelRegistry) -> None:
        vision = registry.list_by_capability(ModelCapability.VISION)
        assert len(vision) > 0
        assert all(ModelCapability.VISION in m.capabilities for m in vision)

    def test_cheapest_for_capability(self, registry: ModelRegistry) -> None:
        cheapest = registry.cheapest_for_capability(ModelCapability.CHAT)
        assert cheapest is not None

    def test_register_and_unregister(self, registry: ModelRegistry) -> None:
        info = ModelInfo(id="test-model", provider_type="test", display_name="Test")
        registry.register(info)
        assert registry.get("test-model") is not None
        registry.unregister("test-model")
        assert registry.get("test-model") is None

    def test_to_dict(self, registry: ModelRegistry) -> None:
        d = registry.to_dict()
        assert "gpt-4o" in d
        assert "claude-sonnet-4-6" in d


class TestModelRouter:
    def test_exact_route(self, router: ModelRouter) -> None:
        decision = router.route(
            model_id="gpt-4o",
            strategy=RoutingStrategy.EXACT,
        )
        assert decision.model_id == "gpt-4o"
        assert decision.provider_type == "openai"

    def test_capability_route(self, router: ModelRouter) -> None:
        decision = router.route(
            required_capabilities=[ModelCapability.CHAT],
            strategy=RoutingStrategy.CAPABILITY,
        )
        assert decision.provider_type in ("anthropic", "openai", "ollama")

    def test_fastest_route_fallback(self, router: ModelRouter) -> None:
        decision = router.route(
            strategy=RoutingStrategy.FASTEST,
        )
        assert decision.provider_type is not None

    def test_health_summary_empty(self, router: ModelRouter) -> None:
        summary = router.health_summary()
        assert isinstance(summary, dict)
