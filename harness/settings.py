"""Global harness settings loaded from environment / .env."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class HarnessSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    harness_host: str = Field("localhost", alias="HARNESS_HOST")
    harness_port: int = Field(9100, alias="HARNESS_PORT")
    harness_debug: bool = Field(True, alias="HARNESS_DEBUG")

    vite_host: str = Field("localhost", alias="VITE_HOST")
    vite_port: int = Field(9102, alias="VITE_PORT")

    # Security / CORS
    allowed_origins: str = Field(
        "http://localhost:9102,tauri://localhost,http://localhost:1420",
        alias="ALLOWED_ORIGINS",
    )

    # Legacy harness state DB (kept for backwards compatibility)
    state_db_path: str = Field(".harness/state.db", alias="STATE_DB_PATH")
    log_dir: str = Field(".harness/logs", alias="LOG_DIR")

    # VLoop data layer — SQLite by default; override with postgresql+asyncpg://...
    vloop_db_url: str = Field("", alias="VLOOP_DB_URL")

    # Optional: override the .vloop project directory location
    vloop_project_dir: str = Field("", alias="VLOOP_PROJECT_DIR")

    # Vector store
    vector_store_dimensions: int = Field(768, alias="VECTOR_STORE_DIMENSIONS")
    vector_store_backend: str = Field("sqlite-vec", alias="VECTOR_STORE_BACKEND")  # sqlite-vec | memory
    embedding_provider: str = Field("ollama", alias="EMBEDDING_PROVIDER")  # ollama | openai | local
    embedding_model: str = Field("nomic-embed-text", alias="EMBEDDING_MODEL")

    # Self-improvement / optimization
    optimization_target_score: float = Field(0.85, alias="OPTIMIZATION_TARGET_SCORE")
    optimization_max_iterations: int = Field(3, alias="OPTIMIZATION_MAX_ITERATIONS")
    optimization_teleprompter: str = Field("BootstrapFewShot", alias="OPTIMIZATION_TELEPROMPTER")

    # Cron / Scheduler
    cron_scheduler_backend: str = Field("asyncio", alias="CRON_SCHEDULER_BACKEND")
