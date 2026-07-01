"""Provider_Router — policy-based provider selection and fallback ordering.

The Provider_Router is the component of the Inference_Gateway that turns a
:class:`~core.orchestration_types.RoutingPolicy` and a current
:class:`ProviderHealth` snapshot into an ordered list of provider candidates the
gateway should try, in order, for a single model call.

It is **pure**: it issues no model call, starts no Kernel workload, and holds no
state. :meth:`ProviderRouter.select` is a deterministic function of its inputs.

Ordering rules
--------------
The configured ``fallback_order`` (a list of provider ids) defines the universe
of candidate providers and their baseline ordering. When it is empty, every
provider present in the supplied :class:`ProviderHealth` is considered instead.

* **Health first** — providers reported unavailable in the health snapshot are
  excluded from the result; only eligible (available) providers are returned so
  the gateway never wastes an attempt on a provider known to be down
  (Requirement 6.3's "next provider in the configured fallback order" is
  evaluated over the providers that can actually serve the call).
* **Preference next** — among eligible providers the order honors the policy's
  optimization preference (Requirement 19.1):
    * ``cost``    -> ascending estimated cost-per-token (cheapest first);
    * ``speed``   -> ascending latency (fastest first);
    * ``quality`` -> descending quality score (best first).
* **Configured order breaks ties** — providers that compare equal on the
  preference metric (including the common case where no metrics are supplied and
  every metric is its default) retain their position in the configured
  ``fallback_order`` (Requirement 6.3). With no metric data at all the result is
  exactly the configured fallback order, filtered to the available providers.

The first element of the returned list is therefore the best provider for the
policy's preference among the eligible providers (Requirement 6.1), and the
remaining elements form the fallback sequence the gateway walks on failure
(Requirement 6.3).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from core.orchestration_types import RoutingPolicy

_VALID_PREFERENCES: frozenset[str] = frozenset({"cost", "speed", "quality"})


@dataclass(slots=True)
class ProviderMetrics:
    """Per-provider health and routing metrics for a single provider.

    ``available`` reflects current provider health; unavailable providers are
    excluded from routing candidates. The remaining fields are the metrics the
    routing preference is evaluated against. Defaults are neutral so a provider
    with no recorded metrics simply keeps its configured fallback position.
    """

    available: bool = True
    cost_per_token: float = 0.0  # lower is cheaper (cost preference)
    latency_ms: float = 0.0  # lower is faster (speed preference)
    quality_score: float = 0.0  # higher is better (quality preference)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ProviderHealth:
    """A snapshot of provider availability and routing metrics.

    Maps a provider id to its :class:`ProviderMetrics`. Providers absent from
    the map are treated as available with neutral metrics, so a sparsely
    populated snapshot degrades to pure configured-fallback ordering.
    """

    providers: dict[str, ProviderMetrics] = field(default_factory=dict)

    def metrics_for(self, provider_id: str) -> ProviderMetrics:
        """Return recorded metrics for ``provider_id`` or neutral defaults."""
        return self.providers.get(provider_id, ProviderMetrics())

    def is_available(self, provider_id: str) -> bool:
        """True when the provider is present-and-available or simply unknown."""
        return self.metrics_for(provider_id).available

    def to_dict(self) -> dict[str, Any]:
        return {pid: m.to_dict() for pid, m in self.providers.items()}


class ProviderRouter:
    """Selects an ordered list of provider candidates for a routing policy."""

    def select(self, policy: RoutingPolicy, health: ProviderHealth) -> list[str]:
        """Return ordered provider candidates for ``policy`` given ``health``.

        Honors the cost|speed|quality preference (Requirement 19.1) and the
        configured fallback order (Requirement 6.3), excluding providers the
        health snapshot reports as unavailable. The first candidate is the best
        eligible provider for the preference (Requirement 6.1).
        """
        # The configured fallback order defines the candidate universe; when it
        # is empty we consider every provider we have health data for.
        if policy.fallback_order:
            universe = list(policy.fallback_order)
        else:
            universe = list(health.providers.keys())

        # De-duplicate while preserving the configured ordering, which doubles
        # as the stable tie-breaker (Requirement 6.3).
        seen: set[str] = set()
        ordered_universe: list[str] = []
        for provider_id in universe:
            if provider_id not in seen:
                seen.add(provider_id)
                ordered_universe.append(provider_id)

        # Factor provider health: drop providers known to be unavailable.
        eligible = [pid for pid in ordered_universe if health.is_available(pid)]

        preference = policy.preference if policy.preference in _VALID_PREFERENCES else None
        if preference is None:
            # Unknown/absent preference -> honor configured fallback order only.
            return eligible

        # Stable sort by the preference metric; ties keep configured order.
        return sorted(
            eligible,
            key=lambda pid: self._preference_key(preference, health.metrics_for(pid)),
        )

    @staticmethod
    def _preference_key(preference: str, metrics: ProviderMetrics) -> float:
        """Sort key for ``preference`` where smaller sorts earlier.

        Cost and speed prefer smaller values directly; quality prefers larger
        scores, so its score is negated to keep "smaller sorts earlier".
        """
        if preference == "cost":
            return metrics.cost_per_token
        if preference == "speed":
            return metrics.latency_ms
        # quality
        return -metrics.quality_score
