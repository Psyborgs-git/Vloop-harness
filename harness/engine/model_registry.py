"""ModelRegistry — discover, register, and query AI model metadata.

Supports static definitions for cloud providers and dynamic discovery
for Ollama. Each model entry carries capability tags, context window,
token pricing hints, and provider routing info.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import httpx


class ModelCapability(StrEnum):
    CHAT = "chat"
    COMPLETION = "completion"
    VISION = "vision"
    TOOL_USE = "tool_use"
    JSON_MODE = "json_mode"
    EMBEDDING = "embedding"
    FUNCTION_CALLING = "function_calling"


@dataclass
class ModelInfo:
    """Metadata for a single model variant."""

    id: str
    provider_type: str
    display_name: str
    context_window: int = 4096
    max_output_tokens: int = 4096
    capabilities: set[ModelCapability] = field(default_factory=set)
    pricing_prompt_per_1k: float = 0.0
    pricing_completion_per_1k: float = 0.0
    supports_streaming: bool = True
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "provider_type": self.provider_type,
            "display_name": self.display_name,
            "context_window": self.context_window,
            "max_output_tokens": self.max_output_tokens,
            "capabilities": [c.value for c in self.capabilities],
            "pricing_prompt_per_1k": self.pricing_prompt_per_1k,
            "pricing_completion_per_1k": self.pricing_completion_per_1k,
            "supports_streaming": self.supports_streaming,
            "extra": self.extra,
        }


# ── Static catalog (cloud providers) ───────────────────────────────────────────

_STATIC_CATALOG: list[ModelInfo] = [
    # Anthropic
    ModelInfo(
        id="claude-sonnet-4-6",
        provider_type="anthropic",
        display_name="Claude Sonnet 4.6",
        context_window=200_000,
        max_output_tokens=8192,
        capabilities={ModelCapability.CHAT, ModelCapability.TOOL_USE, ModelCapability.JSON_MODE},
        pricing_prompt_per_1k=0.003,
        pricing_completion_per_1k=0.015,
    ),
    ModelInfo(
        id="claude-opus-4-6",
        provider_type="anthropic",
        display_name="Claude Opus 4.6",
        context_window=200_000,
        max_output_tokens=8192,
        capabilities={ModelCapability.CHAT, ModelCapability.TOOL_USE, ModelCapability.JSON_MODE},
        pricing_prompt_per_1k=0.015,
        pricing_completion_per_1k=0.075,
    ),
    ModelInfo(
        id="claude-haiku-4-6",
        provider_type="anthropic",
        display_name="Claude Haiku 4.6",
        context_window=200_000,
        max_output_tokens=4096,
        capabilities={ModelCapability.CHAT, ModelCapability.TOOL_USE},
        pricing_prompt_per_1k=0.00025,
        pricing_completion_per_1k=0.00125,
    ),
    # OpenAI
    ModelInfo(
        id="gpt-4o",
        provider_type="openai",
        display_name="GPT-4o",
        context_window=128_000,
        max_output_tokens=16_384,
        capabilities={ModelCapability.CHAT, ModelCapability.VISION, ModelCapability.TOOL_USE, ModelCapability.JSON_MODE, ModelCapability.FUNCTION_CALLING},
        pricing_prompt_per_1k=0.005,
        pricing_completion_per_1k=0.015,
    ),
    ModelInfo(
        id="gpt-4o-mini",
        provider_type="openai",
        display_name="GPT-4o Mini",
        context_window=128_000,
        max_output_tokens=16_384,
        capabilities={ModelCapability.CHAT, ModelCapability.VISION, ModelCapability.TOOL_USE, ModelCapability.JSON_MODE, ModelCapability.FUNCTION_CALLING},
        pricing_prompt_per_1k=0.00015,
        pricing_completion_per_1k=0.0006,
    ),
    ModelInfo(
        id="o3-mini",
        provider_type="openai",
        display_name="o3 Mini",
        context_window=200_000,
        max_output_tokens=100_000,
        capabilities={ModelCapability.CHAT, ModelCapability.TOOL_USE, ModelCapability.JSON_MODE},
        pricing_prompt_per_1k=0.0011,
        pricing_completion_per_1k=0.0044,
    ),
    ModelInfo(
        id="text-embedding-3-small",
        provider_type="openai",
        display_name="Text Embedding 3 Small",
        context_window=8191,
        capabilities={ModelCapability.EMBEDDING},
        pricing_prompt_per_1k=0.00002,
    ),
    ModelInfo(
        id="text-embedding-3-large",
        provider_type="openai",
        display_name="Text Embedding 3 Large",
        context_window=8191,
        capabilities={ModelCapability.EMBEDDING},
        pricing_prompt_per_1k=0.00013,
    ),
]


class ModelRegistry:
    """Holds model metadata and can discover Ollama models dynamically."""

    def __init__(self) -> None:
        self._models: dict[str, ModelInfo] = {}
        for m in _STATIC_CATALOG:
            self._models[m.id] = m

    # ── Registration ──────────────────────────────────────────────────────────

    def register(self, info: ModelInfo) -> None:
        self._models[info.id] = info

    def unregister(self, model_id: str) -> None:
        self._models.pop(model_id, None)

    # ── Queries ───────────────────────────────────────────────────────────────

    def get(self, model_id: str) -> ModelInfo | None:
        return self._models.get(model_id)

    def list_all(self) -> list[ModelInfo]:
        return list(self._models.values())

    def list_by_provider(self, provider_type: str) -> list[ModelInfo]:
        return [m for m in self._models.values() if m.provider_type == provider_type]

    def list_by_capability(self, capability: ModelCapability) -> list[ModelInfo]:
        return [m for m in self._models.values() if capability in m.capabilities]

    def cheapest_for_capability(self, capability: ModelCapability) -> ModelInfo | None:
        candidates = self.list_by_capability(capability)
        if not candidates:
            return None
        return min(candidates, key=lambda m: m.pricing_prompt_per_1k + m.pricing_completion_per_1k)

    def largest_context_for_provider(self, provider_type: str) -> ModelInfo | None:
        candidates = self.list_by_provider(provider_type)
        if not candidates:
            return None
        return max(candidates, key=lambda m: m.context_window)

    # ── Dynamic discovery ─────────────────────────────────────────────────────

    async def discover_ollama(self, base_url: str = "http://localhost:11434") -> list[ModelInfo]:
        """Query Ollama /api/tags and register discovered models."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{base_url}/api/tags")
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            return []

        discovered: list[ModelInfo] = []
        for entry in data.get("models", []):
            name = entry.get("name", "")
            if not name:
                continue
            info = ModelInfo(
                id=name,
                provider_type="ollama",
                display_name=name,
                context_window=entry.get("details", {}).get("context_length", 4096),
                capabilities={ModelCapability.CHAT},
                extra={"ollama_base_url": base_url, "ollama_data": entry},
            )
            self.register(info)
            discovered.append(info)
        return discovered

    def to_dict(self) -> dict[str, dict[str, Any]]:
        return {m.id: m.to_dict() for m in self._models.values()}
