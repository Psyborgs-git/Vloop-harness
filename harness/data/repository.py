"""Repository — the single data-access layer over all ORM models.

Every public method is async. Callers pass in an AsyncSession and this class
handles all ORM interactions, keeping business logic out of route handlers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from harness.data.models import (
    ChatMessage,
    ChatSession,
    DSPyComponentDef,
    PipelineDef,
    ProviderConfigDB,
    TelemetryEvent,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Repository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Chat sessions ─────────────────────────────────────────────────────────

    async def create_session(
        self, title: str = "New Chat", provider_id: str | None = None
    ) -> ChatSession:
        s = ChatSession(title=title, provider_id=provider_id)
        self.session.add(s)
        await self.session.commit()
        await self.session.refresh(s)
        return s

    async def list_sessions(self) -> list[ChatSession]:
        result = await self.session.execute(
            select(ChatSession).order_by(ChatSession.updated_at.desc())
        )
        return list(result.scalars().all())

    async def get_session(self, session_id: str) -> ChatSession | None:
        result = await self.session.execute(
            select(ChatSession)
            .options(selectinload(ChatSession.messages))
            .where(ChatSession.id == session_id)
        )
        return result.scalar_one_or_none()

    async def update_session_title(self, session_id: str, title: str) -> None:
        await self.session.execute(
            update(ChatSession)
            .where(ChatSession.id == session_id)
            .values(title=title, updated_at=_utcnow())
        )
        await self.session.commit()

    async def delete_session(self, session_id: str) -> None:
        s = await self.session.get(ChatSession, session_id)
        if s:
            await self.session.delete(s)
            await self.session.commit()

    # ── Chat messages ─────────────────────────────────────────────────────────

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        meta: dict[str, Any] | None = None,
    ) -> ChatMessage:
        m = ChatMessage(session_id=session_id, role=role, content=content, meta=meta)
        self.session.add(m)
        await self.session.execute(
            update(ChatSession)
            .where(ChatSession.id == session_id)
            .values(updated_at=_utcnow())
        )
        await self.session.commit()
        await self.session.refresh(m)
        return m

    async def get_messages(self, session_id: str) -> list[ChatMessage]:
        result = await self.session.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at)
        )
        return list(result.scalars().all())

    # ── DSPy component definitions ────────────────────────────────────────────

    async def save_component(self, component: DSPyComponentDef) -> DSPyComponentDef:
        existing = await self.session.get(DSPyComponentDef, component.id)
        if existing:
            for attr in (
                "name", "description", "signature_fields", "code", "module_type", "is_active"
            ):
                setattr(existing, attr, getattr(component, attr))
            existing.updated_at = _utcnow()
            await self.session.commit()
            return existing
        self.session.add(component)
        await self.session.commit()
        await self.session.refresh(component)
        return component

    async def list_components(self) -> list[DSPyComponentDef]:
        result = await self.session.execute(
            select(DSPyComponentDef).order_by(DSPyComponentDef.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_component(self, component_id: str) -> DSPyComponentDef | None:
        return await self.session.get(DSPyComponentDef, component_id)

    async def delete_component(self, component_id: str) -> None:
        c = await self.session.get(DSPyComponentDef, component_id)
        if c:
            await self.session.delete(c)
            await self.session.commit()

    # ── Pipeline definitions ──────────────────────────────────────────────────

    async def save_pipeline(self, pipeline: PipelineDef) -> PipelineDef:
        existing = await self.session.get(PipelineDef, pipeline.id)
        if existing:
            for attr in ("name", "description", "steps", "is_active"):
                setattr(existing, attr, getattr(pipeline, attr))
            existing.updated_at = _utcnow()
            await self.session.commit()
            return existing
        self.session.add(pipeline)
        await self.session.commit()
        await self.session.refresh(pipeline)
        return pipeline

    async def list_pipelines(self) -> list[PipelineDef]:
        result = await self.session.execute(
            select(PipelineDef).order_by(PipelineDef.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_pipeline(self, pipeline_id: str) -> PipelineDef | None:
        return await self.session.get(PipelineDef, pipeline_id)

    async def delete_pipeline(self, pipeline_id: str) -> None:
        p = await self.session.get(PipelineDef, pipeline_id)
        if p:
            await self.session.delete(p)
            await self.session.commit()

    # ── Provider configurations ───────────────────────────────────────────────

    async def save_provider(self, provider: ProviderConfigDB) -> ProviderConfigDB:
        existing = await self.session.get(ProviderConfigDB, provider.id)
        if existing:
            for attr in (
                "name", "provider_type", "model", "base_url",
                "encrypted_api_key", "extra_config", "is_default",
            ):
                setattr(existing, attr, getattr(provider, attr))
            existing.updated_at = _utcnow()
            await self.session.commit()
            return existing
        self.session.add(provider)
        await self.session.commit()
        await self.session.refresh(provider)
        return provider

    async def list_providers(self) -> list[ProviderConfigDB]:
        result = await self.session.execute(
            select(ProviderConfigDB).order_by(ProviderConfigDB.created_at)
        )
        return list(result.scalars().all())

    async def get_provider(self, provider_id: str) -> ProviderConfigDB | None:
        return await self.session.get(ProviderConfigDB, provider_id)

    async def get_default_provider(self) -> ProviderConfigDB | None:
        result = await self.session.execute(
            select(ProviderConfigDB).where(ProviderConfigDB.is_default == True).limit(1)  # noqa: E712
        )
        return result.scalar_one_or_none()

    async def set_default_provider(self, provider_id: str) -> None:
        """Clear any existing default, then mark the given provider as default."""
        await self.session.execute(
            update(ProviderConfigDB).values(is_default=False)
        )
        await self.session.execute(
            update(ProviderConfigDB)
            .where(ProviderConfigDB.id == provider_id)
            .values(is_default=True, updated_at=_utcnow())
        )
        await self.session.commit()

    async def delete_provider(self, provider_id: str) -> None:
        p = await self.session.get(ProviderConfigDB, provider_id)
        if p:
            await self.session.delete(p)
            await self.session.commit()

    # ── Telemetry ─────────────────────────────────────────────────────────────

    async def record_telemetry(
        self,
        event_type: str,
        component_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        t = TelemetryEvent(event_type=event_type, component_id=component_id, data=data)
        self.session.add(t)
        await self.session.commit()
