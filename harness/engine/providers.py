"""ProviderManager — multi-provider DSPy engine management.

Responsibilities
────────────────
  • Read provider configurations from the database (via Repository).
  • Decrypt API keys using the SecretVault.
  • Configure (or reconfigure) the shared DSPyEngine with the active provider.
  • Expose a simple ``activate(provider_id)`` API to switch providers at runtime.
  • Seed a default Ollama provider on first boot if the DB has no providers.

Default provider
────────────────
Ollama (http://localhost:11434, model llama3.2) is seeded as the default so the
harness works out-of-the-box without any API keys.  The user can add and switch
to cloud providers from the Settings panel.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from harness.engine.config import EngineConfig

if TYPE_CHECKING:
    from harness.data.models import ProviderConfigDB
    from harness.data.repository import Repository
    from harness.engine.dspy_engine import DSPyEngine
    from harness.vloop.encryption import SecretVault

# ── Provider type constants ───────────────────────────────────────────────────

PROVIDER_OLLAMA = "ollama"
PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_OPENAI = "openai"
PROVIDER_CUSTOM = "custom"

DEFAULT_OLLAMA_MODEL = "llama3.2"
DEFAULT_OLLAMA_URL = "http://localhost:11434"


class ProviderManager:
    """Owns provider lifecycle: DB persistence, key encryption, engine wiring."""

    def __init__(self, engine: "DSPyEngine", vault: "SecretVault") -> None:
        self._engine = engine
        self._vault = vault

    # ── Bootstrap ─────────────────────────────────────────────────────────────

    async def seed_defaults(self, repo: "Repository") -> None:
        """Create a default Ollama provider if the DB has no providers yet."""
        providers = await repo.list_providers()
        if providers:
            return

        from harness.data.models import ProviderConfigDB

        default = ProviderConfigDB(
            id=f"provider_{uuid.uuid4().hex[:8]}",
            name="Ollama (local)",
            provider_type=PROVIDER_OLLAMA,
            model=DEFAULT_OLLAMA_MODEL,
            base_url=DEFAULT_OLLAMA_URL,
            encrypted_api_key="",
            extra_config={},
            is_default=True,
        )
        await repo.save_provider(default)

    async def load_default(self, repo: "Repository") -> bool:
        """Configure the DSPy engine from the default provider in DB.

        Returns True if configuration succeeded, False otherwise.
        """
        provider = await repo.get_default_provider()
        if not provider:
            return False
        try:
            self._configure_engine(provider)
            return True
        except Exception:
            return False

    # ── Runtime activation ────────────────────────────────────────────────────

    async def activate(self, provider_id: str, repo: "Repository") -> None:
        """Set *provider_id* as default and reconfigure the engine."""
        provider = await repo.get_provider(provider_id)
        if not provider:
            raise ValueError(f"Provider {provider_id!r} not found")

        await repo.set_default_provider(provider_id)
        self._configure_engine(provider)

    # ── Provider CRUD helpers ─────────────────────────────────────────────────

    def build_provider_record(
        self,
        name: str,
        provider_type: str,
        model: str,
        base_url: str = "",
        api_key: str = "",
        extra_config: dict[str, Any] | None = None,
        provider_id: str | None = None,
    ) -> "ProviderConfigDB":
        """Construct (but do not persist) a ProviderConfigDB with encrypted key."""
        from harness.data.models import ProviderConfigDB

        encrypted_key = self._vault.encrypt(api_key) if api_key else ""
        return ProviderConfigDB(
            id=provider_id or f"provider_{uuid.uuid4().hex[:8]}",
            name=name,
            provider_type=provider_type,
            model=model,
            base_url=base_url,
            encrypted_api_key=encrypted_key,
            extra_config=extra_config or {},
            is_default=False,
        )

    def provider_to_dict(self, provider: "ProviderConfigDB") -> dict[str, Any]:
        """Serialize a provider for the REST API — never exposes the raw API key."""
        return {
            "id": provider.id,
            "name": provider.name,
            "provider_type": provider.provider_type,
            "model": provider.model,
            "base_url": provider.base_url,
            "has_api_key": bool(provider.encrypted_api_key),
            "extra_config": provider.extra_config,
            "is_default": provider.is_default,
            "created_at": provider.created_at.isoformat(),
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _configure_engine(self, provider: "ProviderConfigDB") -> None:
        api_key = (
            self._vault.decrypt(provider.encrypted_api_key)
            if provider.encrypted_api_key
            else ""
        )
        cfg = EngineConfig(
            dspy_lm_provider=provider.provider_type,
            dspy_lm_model=provider.model,
            anthropic_api_key=api_key if provider.provider_type == PROVIDER_ANTHROPIC else "",
            openai_api_key=api_key if provider.provider_type == PROVIDER_OPENAI else "",
            ollama_base_url=provider.base_url or DEFAULT_OLLAMA_URL,
        )

        # Patch extra config if the provider type is "custom" (openai-compatible)
        if provider.provider_type == PROVIDER_CUSTOM and provider.base_url:
            cfg = EngineConfig(
                dspy_lm_provider="openai",
                dspy_lm_model=provider.model,
                openai_api_key=api_key or "none",
                ollama_base_url=provider.base_url,
            )

        import os
        import httpx
        rust_base_url = os.getenv("RUST_BASE_AI_URL")
        if rust_base_url:
            try:
                # Tell the Rust completions engine to update its active provider
                config_url = rust_base_url.replace("/v1", "/harness/configure_provider")
                httpx.post(
                    config_url,
                    json={
                        "provider_type": provider.provider_type,
                        "model": provider.model,
                        "api_key": api_key,
                        "base_url": provider.base_url or "",
                    },
                    timeout=2.0
                )
            except Exception:
                pass

        self._engine.reconfigure(cfg)
