"""ModelRouter — intelligent provider selection, fallback chains, and load balancing.

Given a request profile (model_id, required capabilities, preferred provider),
the router returns the best provider configuration. If the primary fails,
it walks a fallback chain.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx

from harness.engine.model_registry import ModelCapability, ModelInfo, ModelRegistry


class RoutingStrategy(str, Enum):
    EXACT = "exact"           # Use the requested model_id exactly
    CAPABILITY = "capability"  # Pick cheapest model with required capabilities
    PROVIDER = "provider"      # Pick largest context model for a provider
    FASTEST = "fastest"        # Pick model with lowest observed latency


@dataclass
class RoutingDecision:
    """Result of a routing decision."""

    provider_type: str
    model_id: str
    base_url: str = ""
    api_key: str = ""
    reasoning: str = ""
    estimated_cost_per_1k: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_type": self.provider_type,
            "model_id": self.model_id,
            "base_url": self.base_url,
            "reasoning": self.reasoning,
            "estimated_cost_per_1k": self.estimated_cost_per_1k,
        }


class ProviderHealth:
    """Tracks latency and error rates per provider endpoint."""

    def __init__(self) -> None:
        self._latencies: dict[str, list[float]] = {}
        self._errors: dict[str, int] = {}
        self._last_success: dict[str, float] = {}

    def record_latency(self, provider_type: str, latency_ms: float) -> None:
        self._latencies.setdefault(provider_type, []).append(latency_ms)
        # Keep last 20 samples
        self._latencies[provider_type] = self._latencies[provider_type][-20:]
        self._last_success[provider_type] = time.time()

    def record_error(self, provider_type: str) -> None:
        self._errors[provider_type] = self._errors.get(provider_type, 0) + 1

    def avg_latency(self, provider_type: str) -> float:
        samples = self._latencies.get(provider_type, [])
        if not samples:
            return float("inf")
        return sum(samples) / len(samples)

    def error_rate(self, provider_type: str) -> float:
        samples = len(self._latencies.get(provider_type, []))
        errors = self._errors.get(provider_type, 0)
        total = samples + errors
        if total == 0:
            return 0.0
        return errors / total

    def is_healthy(self, provider_type: str) -> bool:
        return self.error_rate(provider_type) < 0.5


class ModelRouter:
    """Routes AI requests to the best available provider/model."""

    def __init__(
        self,
        registry: ModelRegistry | None = None,
        default_provider: str = "ollama",
    ) -> None:
        self.registry = registry or ModelRegistry()
        self.default_provider = default_provider
        self._health = ProviderHealth()
        self._fallback_chains: dict[str, list[str]] = {
            "anthropic": ["openai", "ollama"],
            "openai": ["anthropic", "ollama"],
            "ollama": ["openai", "anthropic"],
        }

    # ── Configuration ─────────────────────────────────────────────────────────

    def set_fallback_chain(self, provider_type: str, chain: list[str]) -> None:
        self._fallback_chains[provider_type] = chain

    # ── Routing ───────────────────────────────────────────────────────────────

    def route(
        self,
        model_id: str | None = None,
        required_capabilities: list[ModelCapability] | None = None,
        strategy: RoutingStrategy = RoutingStrategy.EXACT,
        preferred_provider: str | None = None,
        provider_configs: list[dict[str, Any]] | None = None,
    ) -> RoutingDecision:
        """Pick the best provider/model for a request."""

        provider_configs = provider_configs or []
        cap_set = set(required_capabilities or [ModelCapability.CHAT])

        # 1. Exact match
        if strategy == RoutingStrategy.EXACT and model_id:
            info = self.registry.get(model_id)
            if info:
                cfg = self._find_provider_config(info.provider_type, provider_configs)
                return RoutingDecision(
                    provider_type=info.provider_type,
                    model_id=info.id,
                    base_url=cfg.get("base_url", "") if cfg else "",
                    api_key=cfg.get("api_key", "") if cfg else "",
                    reasoning=f"Exact match for {model_id}",
                    estimated_cost_per_1k=info.pricing_prompt_per_1k + info.pricing_completion_per_1k,
                )

        # 2. Capability-based (cheapest)
        if strategy == RoutingStrategy.CAPABILITY:
            candidates = [
                m for m in self.registry.list_all()
                if cap_set.issubset(m.capabilities) and self._health.is_healthy(m.provider_type)
            ]
            if candidates:
                best = min(candidates, key=lambda m: m.pricing_prompt_per_1k + m.pricing_completion_per_1k)
                cfg = self._find_provider_config(best.provider_type, provider_configs)
                return RoutingDecision(
                    provider_type=best.provider_type,
                    model_id=best.id,
                    base_url=cfg.get("base_url", "") if cfg else "",
                    api_key=cfg.get("api_key", "") if cfg else "",
                    reasoning=f"Cheapest model with capabilities {cap_set}",
                    estimated_cost_per_1k=best.pricing_prompt_per_1k + best.pricing_completion_per_1k,
                )

        # 3. Provider-based (largest context)
        if strategy == RoutingStrategy.PROVIDER and preferred_provider:
            best = self.registry.largest_context_for_provider(preferred_provider)
            if best:
                cfg = self._find_provider_config(best.provider_type, provider_configs)
                return RoutingDecision(
                    provider_type=best.provider_type,
                    model_id=best.id,
                    base_url=cfg.get("base_url", "") if cfg else "",
                    api_key=cfg.get("api_key", "") if cfg else "",
                    reasoning=f"Largest context model for {preferred_provider}",
                    estimated_cost_per_1k=best.pricing_prompt_per_1k + best.pricing_completion_per_1k,
                )

        # 4. Fastest (lowest observed latency)
        if strategy == RoutingStrategy.FASTEST:
            healthy = [m for m in self.registry.list_all() if self._health.is_healthy(m.provider_type)]
            if healthy:
                best = min(healthy, key=lambda m: self._health.avg_latency(m.provider_type))
                cfg = self._find_provider_config(best.provider_type, provider_configs)
                return RoutingDecision(
                    provider_type=best.provider_type,
                    model_id=best.id,
                    base_url=cfg.get("base_url", "") if cfg else "",
                    api_key=cfg.get("api_key", "") if cfg else "",
                    reasoning=f"Fastest healthy provider ({best.provider_type})",
                    estimated_cost_per_1k=best.pricing_prompt_per_1k + best.pricing_completion_per_1k,
                )

        # Fallback: default provider
        return RoutingDecision(
            provider_type=self.default_provider,
            model_id="llama3.2",
            reasoning="No suitable model found; using default",
        )

    # ── Fallback execution ──────────────────────────────────────────────────

    async def execute_with_fallback(
        self,
        fn: Any,
        primary_decision: RoutingDecision,
        provider_configs: list[dict[str, Any]] | None = None,
    ) -> Any:
        """Execute *fn* with the primary decision; on failure walk fallback chain."""
        chain = [primary_decision.provider_type] + self._fallback_chains.get(
            primary_decision.provider_type, []
        )
        last_exc: Exception | None = None
        for provider_type in chain:
            cfg = self._find_provider_config(provider_type, provider_configs or [])
            try:
                t0 = time.time()
                result = await fn(provider_type, cfg)
                self._health.record_latency(provider_type, (time.time() - t0) * 1000)
                return result
            except Exception as exc:
                self._health.record_error(provider_type)
                last_exc = exc
        raise RuntimeError(f"All providers in fallback chain failed: {last_exc}") from last_exc

    # ── Health probes ───────────────────────────────────────────────────────

    async def probe_provider(self, provider_type: str, base_url: str = "", api_key: str = "") -> bool:
        """Quick health check for a provider."""
        if provider_type == "ollama":
            url = base_url or "http://localhost:11434"
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    r = await client.get(f"{url}/api/tags")
                    return r.status_code == 200
            except Exception:
                return False
        # Cloud providers: minimal ping
        try:
            # We can't easily ping Anthropic/OpenAI without a key and a real call,
            # so we assume healthy unless proven otherwise via execute_with_fallback.
            return True
        except Exception:
            return False

    # ── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _find_provider_config(
        provider_type: str, configs: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        for cfg in configs:
            if cfg.get("provider_type") == provider_type:
                return cfg
        return None

    def health_summary(self) -> dict[str, dict[str, Any]]:
        """Return health stats for all observed providers."""
        summary: dict[str, dict[str, Any]] = {}
        all_providers = set(list(self._health._latencies.keys()) + list(self._health._errors.keys()))
        for p in all_providers:
            summary[p] = {
                "avg_latency_ms": round(self._health.avg_latency(p), 2),
                "error_rate": round(self._health.error_rate(p), 4),
                "healthy": self._health.is_healthy(p),
            }
        return summary
