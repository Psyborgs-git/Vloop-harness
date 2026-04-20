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
    harness_port: int = Field(8000, alias="HARNESS_PORT")
    harness_debug: bool = Field(True, alias="HARNESS_DEBUG")

    vite_host: str = Field("localhost", alias="VITE_HOST")
    vite_port: int = Field(5173, alias="VITE_PORT")

    state_db_path: str = Field(".harness/state.db", alias="STATE_DB_PATH")
    log_dir: str = Field(".harness/logs", alias="LOG_DIR")
