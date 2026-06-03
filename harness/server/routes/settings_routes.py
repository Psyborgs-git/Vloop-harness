"""REST routes for global settings and provider configuration.

Endpoints
─────────
  GET    /api/settings                       — get global settings JSON
  PUT    /api/settings                       — update global settings
  GET    /api/providers                      — list provider configs
  POST   /api/providers                      — create a provider
  GET    /api/providers/{id}                 — get a provider (no API key in response)
  PUT    /api/providers/{id}                 — update a provider
  DELETE /api/providers/{id}                 — delete a provider
  POST   /api/providers/{id}/set-default     — activate a provider
  GET    /api/providers/{id}/test            — test provider connectivity
  GET    /api/ollama/models                  — list available Ollama models
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from harness.data.db import get_session
from harness.data.repository import Repository

router = APIRouter(tags=["settings"])


# ── Request models ────────────────────────────────────────────────────────────


class SettingsUpdateRequest(BaseModel):
    settings: dict[str, Any]


class ProviderCreateRequest(BaseModel):
    name: str
    provider_type: str  # ollama | anthropic | openai | custom
    model: str
    base_url: str = ""
    api_key: str = ""
    extra_config: dict[str, Any] = {}


class ProviderUpdateRequest(BaseModel):
    name: str | None = None
    provider_type: str | None = None
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    extra_config: dict[str, Any] | None = None


# ── Global settings ───────────────────────────────────────────────────────────


@router.get("/api/settings")
async def get_settings(request: Request) -> dict[str, Any]:
    storage = request.app.state.vloop_storage
    return storage.load_global_settings()


@router.put("/api/settings")
async def update_settings(
    body: SettingsUpdateRequest,
    request: Request,
) -> dict[str, Any]:
    storage = request.app.state.vloop_storage
    current = storage.load_global_settings()
    merged = {**current, **body.settings}
    storage.save_global_settings(merged)
    return merged


# ── Provider CRUD ─────────────────────────────────────────────────────────────


@router.get("/api/providers")
async def list_providers(
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    repo = Repository(db)
    providers = await repo.list_providers()
    pm = request.app.state.provider_manager
    return [pm.provider_to_dict(p) for p in providers]


@router.post("/api/providers", status_code=201)
async def create_provider(
    body: ProviderCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    pm = request.app.state.provider_manager
    record = pm.build_provider_record(
        name=body.name,
        provider_type=body.provider_type,
        model=body.model,
        base_url=body.base_url,
        api_key=body.api_key,
        extra_config=body.extra_config,
    )
    repo = Repository(db)
    saved = await repo.save_provider(record)
    return pm.provider_to_dict(saved)


@router.get("/api/providers/{provider_id}")
async def get_provider(
    provider_id: str,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    repo = Repository(db)
    provider = await repo.get_provider(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    pm = request.app.state.provider_manager
    return pm.provider_to_dict(provider)


@router.put("/api/providers/{provider_id}")
async def update_provider(
    provider_id: str,
    body: ProviderUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    repo = Repository(db)
    provider = await repo.get_provider(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    pm = request.app.state.provider_manager
    vault = request.app.state.vault

    if body.name is not None:
        provider.name = body.name
    if body.provider_type is not None:
        provider.provider_type = body.provider_type
    if body.model is not None:
        provider.model = body.model
    if body.base_url is not None:
        provider.base_url = body.base_url
    if body.api_key is not None:
        provider.encrypted_api_key = vault.encrypt(body.api_key) if body.api_key else ""
    if body.extra_config is not None:
        provider.extra_config = body.extra_config

    saved = await repo.save_provider(provider)

    # If this is the default, reconfigure the engine
    if saved.is_default:
        try:
            await pm.activate(provider_id, repo)
        except Exception:
            pass

    return pm.provider_to_dict(saved)


@router.delete("/api/providers/{provider_id}", status_code=204)
async def delete_provider(
    provider_id: str,
    db: AsyncSession = Depends(get_session),
) -> None:
    repo = Repository(db)
    provider = await repo.get_provider(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    await repo.delete_provider(provider_id)


@router.post("/api/providers/{provider_id}/set-default")
async def set_default_provider(
    provider_id: str,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    repo = Repository(db)
    provider = await repo.get_provider(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    pm = request.app.state.provider_manager
    try:
        await pm.activate(provider_id, repo)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Provider activated in DB but engine configuration failed: {exc}",
        ) from exc

    provider = await repo.get_provider(provider_id)
    return pm.provider_to_dict(provider)  # type: ignore[arg-type]


@router.get("/api/providers/{provider_id}/test")
async def test_provider(
    provider_id: str,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Quick connectivity check — attempts a tiny LM call against the provider."""
    repo = Repository(db)
    provider = await repo.get_provider(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    vault = request.app.state.vault

    api_key = vault.decrypt(provider.encrypted_api_key) if provider.encrypted_api_key else ""

    from harness.engine.config import EngineConfig
    from harness.engine.dspy_engine import DSPyEngine

    try:
        cfg = EngineConfig(
            dspy_lm_provider=provider.provider_type,
            dspy_lm_model=provider.model,
            anthropic_api_key=api_key if provider.provider_type == "anthropic" else "",
            openai_api_key=api_key if provider.provider_type == "openai" else "",
            ollama_base_url=provider.base_url or "http://localhost:11434",
        )
        test_engine = DSPyEngine(cfg)
        test_engine.configure()
        result = await test_engine.complete("Reply with just the word: OK")
        return {"status": "ok", "response": result[:100]}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


# ── Ollama model discovery ────────────────────────────────────────────────────


@router.get("/api/ollama/models")
async def list_ollama_models(base_url: str = "http://localhost:11434") -> dict[str, Any]:
    """Return the list of locally available Ollama models."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{base_url}/api/tags")
            r.raise_for_status()
            data = r.json()
            models = [m["name"] for m in data.get("models", [])]
            return {"status": "ok", "models": models, "base_url": base_url}
    except Exception as exc:
        return {"status": "error", "models": [], "detail": str(exc)}
