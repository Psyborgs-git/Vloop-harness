"""Provider type definitions and catalog."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(slots=True)
class ProviderTypeSpec:
    key: str
    label: str
    description: str
    secret_modes: list[str]
    default_model: str
    model_examples: list[str]
    api_base_hint: str | None = None
    api_version_hint: str | None = None
    requires_secret: bool = True
    local_only_http: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


PROVIDER_TYPES: dict[str, ProviderTypeSpec] = {
    "mock": ProviderTypeSpec(
        key="mock",
        label="VLoop Mock LM",
        description="Local deterministic DSPy-compatible provider for smoke testing and first-run exploration.",
        secret_modes=["none"],
        default_model="mock/echo-agent",
        model_examples=["mock/echo-agent"],
        requires_secret=False,
    ),
    "ollama": ProviderTypeSpec(
        key="ollama",
        label="Ollama",
        description="Use a local Ollama daemon over loopback without any cloud credentials.",
        secret_modes=["none"],
        default_model="ollama/llama3.2",
        model_examples=["ollama/llama3.2", "ollama/qwen2.5:7b"],
        api_base_hint="http://127.0.0.1:11434",
        requires_secret=False,
        local_only_http=True,
    ),
    "openai": ProviderTypeSpec(
        key="openai",
        label="OpenAI",
        description="Use OpenAI-hosted chat or responses models through LiteLLM.",
        secret_modes=["env", "session"],
        default_model="openai/gpt-4o-mini",
        model_examples=["openai/gpt-4o-mini", "openai/gpt-4.1-mini"],
    ),
    "anthropic": ProviderTypeSpec(
        key="anthropic",
        label="Anthropic",
        description="Use Anthropic Claude models through LiteLLM.",
        secret_modes=["env", "session"],
        default_model="anthropic/claude-3-5-sonnet-latest",
        model_examples=[
            "anthropic/claude-3-5-sonnet-latest",
            "anthropic/claude-3-5-haiku-latest",
        ],
    ),
    "openrouter": ProviderTypeSpec(
        key="openrouter",
        label="OpenRouter",
        description="Route OpenAI-compatible traffic through OpenRouter with a provider-prefixed model string.",
        secret_modes=["env", "session"],
        default_model="openrouter/openai/gpt-4o-mini",
        model_examples=[
            "openrouter/openai/gpt-4o-mini",
            "openrouter/anthropic/claude-3.5-sonnet",
        ],
        api_base_hint="https://openrouter.ai/api/v1",
    ),
    "azure": ProviderTypeSpec(
        key="azure",
        label="Azure OpenAI",
        description="Use Azure OpenAI deployments via LiteLLM with an Azure-style deployment model string.",
        secret_modes=["env", "session"],
        default_model="azure/my-deployment",
        model_examples=["azure/my-deployment"],
        api_base_hint="https://your-resource.openai.azure.com",
        api_version_hint="2024-10-21",
    ),
}
