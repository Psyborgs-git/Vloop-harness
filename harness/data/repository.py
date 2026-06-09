"""Repository — the single data-access layer over all ORM models.

Every public method is async. Callers pass in an AsyncSession and this class
handles all ORM interactions, keeping business logic out of route handlers.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from harness.data.models import (
    AgentRun,
    AgentRunStep,
    AppManifest,
    ChatMessage,
    ChatSession,
    ComponentVersion,
    CronJob,
    DSPyComponentDef,
    EvalDataset,
    GeneratedView,
    PipelineDef,
    ProviderConfigDB,
    TelemetryEvent,
    ToolTrace,
    ViewVersion,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


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

    # ── Generated views ───────────────────────────────────────────────────────

    async def save_view(self, view: GeneratedView) -> GeneratedView:
        self.session.add(view)
        await self.session.commit()
        await self.session.refresh(view)
        return view

    async def list_views(self) -> list[GeneratedView]:
        result = await self.session.execute(
            select(GeneratedView).order_by(GeneratedView.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_view(self, view_id: str) -> GeneratedView | None:
        return await self.session.get(GeneratedView, view_id)

    async def delete_view(self, view_id: str) -> None:
        v = await self.session.get(GeneratedView, view_id)
        if v:
            await self.session.delete(v)
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

    # ── Agent runs ────────────────────────────────────────────────────────────

    async def create_agent_run(
        self,
        goal: str,
        session_id: str | None = None,
        autonomy_mode: str = "suggest",
    ) -> AgentRun:
        run = AgentRun(goal=goal, session_id=session_id, autonomy_mode=autonomy_mode)
        self.session.add(run)
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def get_agent_run(self, run_id: str) -> AgentRun | None:
        result = await self.session.execute(
            select(AgentRun)
            .options(selectinload(AgentRun.steps))
            .where(AgentRun.id == run_id)
        )
        return result.scalar_one_or_none()

    async def list_agent_runs(self, limit: int = 50) -> list[AgentRun]:
        result = await self.session.execute(
            select(AgentRun).order_by(AgentRun.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def update_agent_run(
        self,
        run_id: str,
        **kwargs: Any,
    ) -> None:
        kwargs["updated_at"] = _utcnow()
        await self.session.execute(
            update(AgentRun).where(AgentRun.id == run_id).values(**kwargs)
        )
        await self.session.commit()

    async def delete_agent_run(self, run_id: str) -> None:
        r = await self.session.get(AgentRun, run_id)
        if r:
            await self.session.delete(r)
            await self.session.commit()

    async def add_run_step(
        self,
        run_id: str,
        step_type: str,
        input_data: dict[str, Any] | None = None,
        output_data: dict[str, Any] | None = None,
        tool_name: str | None = None,
        status: str = "completed",
        error: str | None = None,
        confirmation_token: str | None = None,
        duration_ms: int | None = None,
    ) -> AgentRunStep:
        step = AgentRunStep(
            run_id=run_id,
            step_type=step_type,
            tool_name=tool_name,
            input_data=input_data,
            output_data=output_data,
            status=status,
            error=error,
            confirmation_token=confirmation_token,
            duration_ms=duration_ms,
        )
        self.session.add(step)
        await self.session.commit()
        await self.session.refresh(step)
        return step

    # ── App manifests ─────────────────────────────────────────────────────────

    async def create_app_manifest(
        self,
        name: str,
        description: str = "",
        backend_type: str = "pipeline",
        backend_id: str | None = None,
        react_views: list[str] | None = None,
        permissions: list[str] | None = None,
        state_schema: dict[str, Any] | None = None,
        agent_run_id: str | None = None,
    ) -> AppManifest:
        manifest = AppManifest(
            name=name,
            description=description,
            backend_type=backend_type,
            backend_id=backend_id,
            react_views=react_views or [],
            permissions=permissions or [],
            state_schema=state_schema or {},
            agent_run_id=agent_run_id,
        )
        self.session.add(manifest)
        await self.session.commit()
        await self.session.refresh(manifest)
        return manifest

    async def get_app_manifest(self, manifest_id: str) -> AppManifest | None:
        return await self.session.get(AppManifest, manifest_id)

    async def list_app_manifests(self, status: str | None = None) -> list[AppManifest]:
        q = select(AppManifest).order_by(AppManifest.created_at.desc())
        if status:
            q = q.where(AppManifest.status == status)
        result = await self.session.execute(q)
        return list(result.scalars().all())

    async def update_app_manifest(self, manifest_id: str, **kwargs: Any) -> None:
        kwargs["updated_at"] = _utcnow()
        await self.session.execute(
            update(AppManifest).where(AppManifest.id == manifest_id).values(**kwargs)
        )
        await self.session.commit()

    async def delete_app_manifest(self, manifest_id: str) -> None:
        m = await self.session.get(AppManifest, manifest_id)
        if m:
            await self.session.delete(m)
            await self.session.commit()

    # ── Cron Jobs ─────────────────────────────────────────────────────────────

    async def create_cron_job(self, **kwargs: Any) -> CronJob:
        job = CronJob(**kwargs)
        self.session.add(job)
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def get_cron_job(self, job_id: str) -> CronJob | None:
        return await self.session.get(CronJob, job_id)

    async def list_cron_jobs(self, active_only: bool = False) -> list[CronJob]:
        stmt = select(CronJob).order_by(CronJob.created_at.desc())
        if active_only:
            stmt = stmt.where(CronJob.is_active == True)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_cron_job(self, job_id: str, **kwargs: Any) -> CronJob | None:
        job = await self.get_cron_job(job_id)
        if not job:
            return None
        for key, value in kwargs.items():
            setattr(job, key, value)
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def delete_cron_job(self, job_id: str) -> None:
        job = await self.get_cron_job(job_id)
        if job:
            await self.session.delete(job)
            await self.session.commit()

    # ── Tool traces ───────────────────────────────────────────────────────────

    async def record_tool_trace(
        self,
        tool_name: str,
        inputs: dict[str, Any] | None = None,
        outputs: dict[str, Any] | None = None,
        component_id: str | None = None,
        session_id: str | None = None,
        run_step_id: str | None = None,
        risk_level: str = "safe",
        confirmation_token: str | None = None,
        duration_ms: int | None = None,
        success: bool = True,
    ) -> ToolTrace:
        trace = ToolTrace(
            tool_name=tool_name,
            component_id=component_id,
            session_id=session_id,
            run_step_id=run_step_id,
            inputs=inputs,
            outputs=outputs,
            risk_level=risk_level,
            confirmation_token=confirmation_token,
            duration_ms=duration_ms,
            success=success,
        )
        self.session.add(trace)
        await self.session.commit()
        await self.session.refresh(trace)
        return trace

    async def list_tool_traces(
        self,
        tool_name: str | None = None,
        session_id: str | None = None,
        run_step_id: str | None = None,
        limit: int = 100,
    ) -> list[ToolTrace]:
        q = select(ToolTrace).order_by(ToolTrace.created_at.desc()).limit(limit)
        if tool_name:
            q = q.where(ToolTrace.tool_name == tool_name)
        if session_id:
            q = q.where(ToolTrace.session_id == session_id)
        if run_step_id:
            q = q.where(ToolTrace.run_step_id == run_step_id)
        result = await self.session.execute(q)
        return list(result.scalars().all())

    # ── Component versions ────────────────────────────────────────────────────

    async def create_component_version(
        self,
        component_id: str,
        name: str,
        code: str,
        description: str = "",
        module_type: str = "ChainOfThought",
        change_summary: str = "",
    ) -> ComponentVersion:
        """Snapshot a component at its current state, auto-incrementing version_number."""
        result = await self.session.execute(
            select(ComponentVersion)
            .where(ComponentVersion.component_id == component_id)
            .order_by(ComponentVersion.version_number.desc())
            .limit(1)
        )
        latest = result.scalar_one_or_none()
        next_version = (latest.version_number + 1) if latest else 1

        version = ComponentVersion(
            component_id=component_id,
            version_number=next_version,
            name=name,
            description=description,
            code=code,
            module_type=module_type,
            change_summary=change_summary,
        )
        self.session.add(version)
        await self.session.commit()
        await self.session.refresh(version)
        return version

    async def list_component_versions(self, component_id: str) -> list[ComponentVersion]:
        result = await self.session.execute(
            select(ComponentVersion)
            .where(ComponentVersion.component_id == component_id)
            .order_by(ComponentVersion.version_number.desc())
        )
        return list(result.scalars().all())

    async def get_component_version(self, version_id: str) -> ComponentVersion | None:
        return await self.session.get(ComponentVersion, version_id)

    # ── View versions ───────────────────────────────────────────────────────────

    async def create_view_version(
        self,
        view_id: str,
        file_path: str,
        source: str,
        prompt: str | None = None,
        agent_run_id: str | None = None,
        change_summary: str = "",
    ) -> ViewVersion:
        """Create a new version of a view."""
        from sqlalchemy import select

        # Get the next version number
        result = await self.session.execute(
            select(ViewVersion)
            .where(ViewVersion.view_id == view_id)
            .order_by(ViewVersion.version_number.desc())
        )
        last_version = result.scalars().first()
        next_version = (last_version.version_number + 1) if last_version else 1

        version = ViewVersion(
            view_id=view_id,
            version_number=next_version,
            file_path=file_path,
            source=source,
            prompt=prompt,
            agent_run_id=agent_run_id,
            change_summary=change_summary,
        )
        self.session.add(version)
        await self.session.commit()
        await self.session.refresh(version)
        return version

    async def list_view_versions(self, view_id: str) -> list[ViewVersion]:
        result = await self.session.execute(
            select(ViewVersion)
            .where(ViewVersion.view_id == view_id)
            .order_by(ViewVersion.version_number.desc())
        )
        return list(result.scalars().all())

    async def get_view_version(self, version_id: str) -> ViewVersion | None:
        return await self.session.get(ViewVersion, version_id)

    # ── Eval datasets ─────────────────────────────────────────────────────────

    async def create_eval_dataset(
        self,
        component_id: str,
        name: str,
        description: str = "",
        examples: list[dict[str, Any]] | None = None,
    ) -> EvalDataset:
        dataset = EvalDataset(
            component_id=component_id,
            name=name,
            description=description,
            examples=examples or [],
        )
        self.session.add(dataset)
        await self.session.commit()
        await self.session.refresh(dataset)
        return dataset

    async def list_eval_datasets(self, component_id: str) -> list[EvalDataset]:
        result = await self.session.execute(
            select(EvalDataset)
            .where(EvalDataset.component_id == component_id)
            .order_by(EvalDataset.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_eval_dataset(self, dataset_id: str) -> EvalDataset | None:
        return await self.session.get(EvalDataset, dataset_id)

    async def update_eval_dataset(self, dataset_id: str, **kwargs: Any) -> None:
        kwargs["updated_at"] = _utcnow()
        await self.session.execute(
            update(EvalDataset).where(EvalDataset.id == dataset_id).values(**kwargs)
        )
        await self.session.commit()

    async def delete_eval_dataset(self, dataset_id: str) -> None:
        d = await self.session.get(EvalDataset, dataset_id)
        if d:
            await self.session.delete(d)
            await self.session.commit()
