"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from harness.server.routes import components, proxy, ws


def create_app(main_process: "MainProcess", settings: "HarnessSettings") -> FastAPI:  # type: ignore[name-defined]
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await main_process.boot()
        yield
        await main_process.shutdown()

    app = FastAPI(
        title="Vloop Harness API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Attach shared state
    app.state.main_process = main_process
    app.state.settings = settings

    # Register routers
    app.include_router(components.router)
    app.include_router(ws.router)
    app.include_router(proxy.router)

    @app.get("/")
    async def root() -> dict[str, str]:
        return {"status": "ok", "service": "vloop-harness"}

    return app
