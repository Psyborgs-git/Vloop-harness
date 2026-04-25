"""FastAPI application factory.

Boot sequence
─────────────
1. VLoopStorage   — creates .vloop/ directories
2. SecretVault    — loads/generates encryption key from ~/.vloop/.key
3. SQLAlchemy DB  — creates tables (metadata.db inside .vloop/)
4. DSPyEngine     — AI engine, starts unconfigured
5. ProviderManager — seeds default Ollama provider, loads it into engine
6. ComponentRegistry + PipelineBuilder — DSPy runtime
7. MainProcess    — component tree, legacy state store, logger
8. Existing legacy routes + new dspy/chat/settings routes
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from harness.server.routes import components, proxy, ws
from harness.server.routes.agent_routes import router as agent_router
from harness.server.routes.app_routes import router as app_router
from harness.server.routes.chat_routes import router as chat_router
from harness.server.routes.dspy_routes import router as dspy_router
from harness.server.routes.eval_routes import router as eval_router
from harness.server.routes.settings_routes import router as settings_router
from harness.server.routes.tool_routes import router as tool_router
from harness.server.routes.views_routes import router as views_router

if TYPE_CHECKING:
    from harness.core.main_process import MainProcess
    from harness.settings import HarnessSettings


def create_app(main_process: "MainProcess", settings: "HarnessSettings") -> FastAPI:

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # ── 1. VLoop directories ──────────────────────────────────────────────
        from harness.vloop.storage import VLoopStorage

        project_path = Path(settings.vloop_project_dir) if settings.vloop_project_dir else None
        storage = VLoopStorage(cwd=project_path)
        app.state.vloop_storage = storage

        # ── 2. Secret vault ───────────────────────────────────────────────────
        from harness.vloop.encryption import SecretVault

        vault = SecretVault(key_path=storage.key_path)
        app.state.vault = vault

        # ── 3. Database ───────────────────────────────────────────────────────
        from harness.data.db import close_db, init_db

        db_url = settings.vloop_db_url or f"sqlite+aiosqlite:///{storage.db_path}"
        await init_db(db_url)

        # ── 4. DSPy engine ────────────────────────────────────────────────────
        from harness.engine.config import EngineConfig
        from harness.engine.dspy_engine import DSPyEngine

        engine_cfg = EngineConfig()
        engine = DSPyEngine(engine_cfg)

        # ── 5. Provider manager — seed + configure engine ─────────────────────
        from harness.engine.providers import ProviderManager
        from harness.data.db import get_session_factory

        pm = ProviderManager(engine=engine, vault=vault)
        app.state.provider_manager = pm

        session_factory = get_session_factory()
        async with session_factory() as db_session:
            from harness.data.repository import Repository

            repo = Repository(db_session)
            await pm.seed_defaults(repo)
            configured = await pm.load_default(repo)

        if configured:
            main_process.attach_ai_engine(engine)
        else:
            # Engine un-configured but registered so routes can check .is_ready
            main_process._ai_engine = engine

        # ── 6. Component registry + pipeline builder ──────────────────────────
        from harness.engine.component_registry import DSPyComponentRegistry
        from harness.engine.pipeline_builder import PipelineBuilder

        registry = DSPyComponentRegistry()
        builder = PipelineBuilder(registry)
        app.state.component_registry = registry
        app.state.pipeline_builder = builder

        # Pre-load all active component definitions from DB into the registry
        async with session_factory() as db_session:
            repo2 = Repository(db_session)
            for comp_def in await repo2.list_components():
                if comp_def.is_active:
                    try:
                        registry.compile(comp_def)
                    except Exception:
                        pass  # Compile errors are surfaced per-request

        # ── 7. Main process (legacy) ──────────────────────────────────────────
        await main_process.boot()

        # Wire tool registry into the pipeline builder after boot
        builder.tool_registry = main_process.tools

        storage.write_log("info", "VLoop Harness started", db_url=db_url)

        yield

        # ── Shutdown ──────────────────────────────────────────────────────────
        await main_process.shutdown()
        await close_db()
        storage.write_log("info", "VLoop Harness stopped")

    app = FastAPI(
        title="Vloop Harness API",
        version="0.2.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Attach shared state available before lifespan (settings, main_process)
    app.state.main_process = main_process
    app.state.settings = settings

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(components.router)
    app.include_router(ws.router)
    app.include_router(dspy_router)
    app.include_router(chat_router)
    app.include_router(settings_router)
    app.include_router(tool_router)
    app.include_router(views_router)
    app.include_router(agent_router)
    app.include_router(app_router)
    app.include_router(eval_router)
    app.include_router(proxy.router)  # catch-all last

    @app.get("/")
    async def root() -> dict[str, str]:
        return {"status": "ok", "service": "vloop-harness", "version": "0.2.0"}

    return app
