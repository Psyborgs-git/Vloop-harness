"""DynamicConfig — runtime parameter adaptation for the AI engine.

Features:
  • Auto max_tokens based on context window usage
  • Per-request temperature / top_p tuning
  • Context window budget management
  • Token counting via tiktoken (OpenAI models) or heuristic fallback
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import tiktoken

from harness.engine.model_registry import ModelInfo, ModelRegistry


@dataclass
class GenerationConfig:
    """Resolved generation parameters for a single call."""

    model_id: str = ""
    provider_type: str = ""
    temperature: float = 0.7
    max_tokens: int = 2048
    top_p: float | None = None
    top_k: int | None = None
    stop_sequences: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = {
            "model_id": self.model_id,
            "provider_type": self.provider_type,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if self.top_p is not None:
            d["top_p"] = self.top_p
        if self.top_k is not None:
            d["top_k"] = self.top_k
        if self.stop_sequences:
            d["stop_sequences"] = self.stop_sequences
        d.update(self.extra)
        return d


class TokenCounter:
    """Count tokens for OpenAI models; heuristic fallback for others."""

    def __init__(self) -> None:
        self._encoders: dict[str, tiktoken.Encoding] = {}

    def count(self, text: str, model_id: str = "gpt-4o") -> int:
        """Return approximate token count for *text*."""
        # Normalize model name for tiktoken
        tiktoken_model = self._to_tiktoken_model(model_id)
        try:
            enc = self._encoders.setdefault(tiktoken_model, tiktoken.encoding_for_model(tiktoken_model))
            return len(enc.encode(text))
        except Exception:
            # Heuristic fallback: ~4 chars per token
            return max(1, len(text) // 4)

    @staticmethod
    def _to_tiktoken_model(model_id: str) -> str:
        if "gpt-4o" in model_id or "o3" in model_id:
            return "gpt-4o"
        if "gpt-4" in model_id:
            return "gpt-4"
        if "gpt-3.5" in model_id:
            return "gpt-3.5-turbo"
        return "cl100k_base"


class DynamicConfig:
    """Adapts generation parameters based on request characteristics."""

    def __init__(self, registry: ModelRegistry | None = None) -> None:
        self.registry = registry or ModelRegistry()
        self.token_counter = TokenCounter()
        self._default_temperature = 0.7
        self._default_max_tokens_ratio = 0.25  # Use 25% of context window by default

    # ── Public API ────────────────────────────────────────────────────────────

    def resolve(
        self,
        model_id: str,
        prompt_text: str = "",
        preferred_temperature: float | None = None,
        preferred_max_tokens: int | None = None,
        task_type: str = "chat",
    ) -> GenerationConfig:
        """Build a GenerationConfig tuned for the request."""

        info = self.registry.get(model_id)
        if info is None:
            # Graceful fallback
            return GenerationConfig(
                model_id=model_id,
                temperature=preferred_temperature or self._default_temperature,
                max_tokens=preferred_max_tokens or 2048,
            )

        context_window = info.context_window
        prompt_tokens = self.token_counter.count(prompt_text, model_id) if prompt_text else 0

        # Temperature tuning by task type
        temperature = self._resolve_temperature(preferred_temperature, task_type)

        # Max tokens: respect preferred, else auto-calculate from context window
        max_tokens = self._resolve_max_tokens(
            preferred_max_tokens, context_window, prompt_tokens, info.max_output_tokens
        )

        return GenerationConfig(
            model_id=model_id,
            provider_type=info.provider_type,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=0.9 if task_type == "creative" else None,
            extra={"task_type": task_type},
        )

    def adapt_for_context_window(
        self,
        model_id: str,
        messages: list[dict[str, str]],
        reserve_output_tokens: int = 1024,
    ) -> dict[str, Any]:
        """Given a conversation, suggest truncation or model swap if over budget."""
        info = self.registry.get(model_id)
        if info is None:
            return {"action": "unknown_model", "model_id": model_id}

        total_text = "\n".join(f"{m.get('role', '')}: {m.get('content', '')}" for m in messages)
        tokens = self.token_counter.count(total_text, model_id)
        budget = info.context_window - reserve_output_tokens

        if tokens <= budget:
            return {
                "action": "ok",
                "tokens_used": tokens,
                "budget": budget,
                "remaining": budget - tokens,
            }

        # Over budget — suggest truncation or model swap
        larger = self._find_larger_context_model(info.provider_type, info.context_window)
        return {
            "action": "truncate_or_swap",
            "tokens_used": tokens,
            "budget": budget,
            "overflow": tokens - budget,
            "suggested_model": larger.id if larger else None,
            "truncate_messages": max(1, len(messages) - 2),
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _resolve_temperature(
        self, preferred: float | None, task_type: str
    ) -> float:
        if preferred is not None:
            return preferred
        mapping = {
            "chat": 0.7,
            "creative": 0.9,
            "code": 0.2,
            "extraction": 0.1,
            "classification": 0.1,
            "summarization": 0.3,
        }
        return mapping.get(task_type, self._default_temperature)

    def _resolve_max_tokens(
        self,
        preferred: int | None,
        context_window: int,
        prompt_tokens: int,
        model_max_output: int,
    ) -> int:
        if preferred is not None:
            return min(preferred, model_max_output, context_window - prompt_tokens - 1)

        available = context_window - prompt_tokens
        target = int(context_window * self._default_max_tokens_ratio)
        return min(target, model_max_output, available - 1)

    def _find_larger_context_model(
        self, provider_type: str, current_window: int
    ) -> ModelInfo | None:
        candidates = [
            m for m in self.registry.list_by_provider(provider_type)
            if m.context_window > current_window
        ]
        if not candidates:
            # Cross-provider fallback
            candidates = [m for m in self.registry.list_all() if m.context_window > current_window]
        if not candidates:
            return None
        return min(candidates, key=lambda m: m.pricing_prompt_per_1k + m.pricing_completion_per_1k)
