import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import infer, pipeline, module, agent, health
from .api.ws.stream import router as ws_router
from .dspy_core.lm_config import configure_lm
from .dspy_core.module_registry import ModuleRegistry
from .dspy_core.pipeline_registry import PipelineRegistry
from .telemetry.logger import get_logger

logger = get_logger(__name__)

module_registry = ModuleRegistry()
pipeline_registry = PipelineRegistry()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("inference_backend starting")
    configure_lm()
    module_registry.scan()
    pipeline_registry.scan()
    yield
    logger.info("inference_backend shutting down")


app = FastAPI(title="Vloop Inference Backend", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, tags=["health"])
app.include_router(infer.router, tags=["infer"])
app.include_router(pipeline.router, tags=["pipeline"])
app.include_router(module.router, tags=["module"])
app.include_router(agent.router, tags=["agent"])
app.include_router(ws_router, tags=["ws"])

# Expose registries on app state for route handlers
app.state.module_registry = module_registry
app.state.pipeline_registry = pipeline_registry
