"""Engine configuration loaded from environment / .env file."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class EngineConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Provider selection ────────────────────────────────────────────────────
    # Ollama is the default so the harness works out-of-the-box without API keys.
    dspy_lm_provider: str = Field("ollama", alias="DSPY_LM_PROVIDER")
    dspy_lm_model: str = Field("llama3.2", alias="DSPY_LM_MODEL")

    # ── Anthropic ─────────────────────────────────────────────────────────────
    anthropic_api_key: str = Field("", alias="ANTHROPIC_API_KEY")

    # ── OpenAI ────────────────────────────────────────────────────────────────
    openai_api_key: str = Field("", alias="OPENAI_API_KEY")

    # ── Ollama ────────────────────────────────────────────────────────────────
    ollama_base_url: str = Field("http://localhost:11434", alias="OLLAMA_BASE_URL")

    # ── Sampling defaults ─────────────────────────────────────────────────────
    temperature: float = 0.7
    max_tokens: int = 2048

    # ── Caching ───────────────────────────────────────────────────────────────
    cache_enabled: bool = True
    cache_dir: str = Field(".harness/dspy_cache", alias="CACHE_DIR")
