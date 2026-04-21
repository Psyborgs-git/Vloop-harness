"""VLoop directory management.

Creates and manages two directory trees:
  ~/.vloop/       — global/root settings (providers, key, global config)
  ./.vloop/       — project-local data (DB, chats, logs, telemetry, pipelines)
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


class VLoopStorage:
    """Owns the .vloop directory in CWD and the ~/.vloop global directory."""

    def __init__(self, cwd: Path | None = None) -> None:
        self.project_dir = (cwd or Path.cwd()) / ".vloop"
        self.global_dir = Path.home() / ".vloop"
        self._init_dirs()

    # ── Initialisation ────────────────────────────────────────────────────────

    def _init_dirs(self) -> None:
        for d in [
            self.project_dir,
            self.project_dir / "chats",
            self.project_dir / "components",
            self.project_dir / "pipelines",
            self.project_dir / "telemetry",
            self.project_dir / "logs",
            self.global_dir,
            self.global_dir / "logs",
        ]:
            d.mkdir(parents=True, exist_ok=True)

    # ── Well-known paths ─────────────────────────────────────────────────────

    @property
    def db_path(self) -> Path:
        return self.project_dir / "metadata.db"

    @property
    def global_settings_path(self) -> Path:
        return self.global_dir / "settings.json"

    @property
    def key_path(self) -> Path:
        return self.global_dir / ".key"

    @property
    def permissions_log_path(self) -> Path:
        return self.project_dir / "permissions.jsonl"

    # ── Global settings ──────────────────────────────────────────────────────

    def load_global_settings(self) -> dict[str, Any]:
        if not self.global_settings_path.exists():
            return {}
        with open(self.global_settings_path) as f:
            return json.load(f)

    def save_global_settings(self, settings: dict[str, Any]) -> None:
        with open(self.global_settings_path, "w") as f:
            json.dump(settings, f, indent=2)

    # ── Chat JSONL files ─────────────────────────────────────────────────────

    def chat_session_file(self, session_id: str) -> Path:
        return self.project_dir / "chats" / f"{session_id}.jsonl"

    def append_chat_message(self, session_id: str, message: dict[str, Any]) -> None:
        with open(self.chat_session_file(session_id), "a") as f:
            f.write(
                json.dumps({**message, "timestamp": _utc_now()}) + "\n"
            )

    def read_chat_session(self, session_id: str) -> list[dict[str, Any]]:
        path = self.chat_session_file(session_id)
        if not path.exists():
            return []
        messages: list[dict[str, Any]] = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    messages.append(json.loads(line))
        return messages

    def archive_chat_session(self, session_id: str) -> None:
        """Rename the JSONL transcript to ``{session_id}.jsonl.deleted`` for soft retention."""
        src = self.chat_session_file(session_id)
        if not src.exists():
            return

        dst = src.with_suffix(".jsonl.deleted")
        if dst.exists():
            dst.unlink()
        src.rename(dst)

    # ── Telemetry JSONL ──────────────────────────────────────────────────────

    def log_telemetry(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        log_file = self.project_dir / "telemetry" / f"{date.today().isoformat()}.jsonl"
        with open(log_file, "a") as f:
            f.write(
                json.dumps({"type": event_type, "data": data or {}, "timestamp": _utc_now()}) + "\n"
            )

    # ── Permissions audit JSONL ───────────────────────────────────────────────

    def log_permission(self, event: dict[str, Any]) -> None:
        with open(self.permissions_log_path, "a") as f:
            f.write(json.dumps({**event, "timestamp": _utc_now()}) + "\n")

    # ── Structured log JSONL ─────────────────────────────────────────────────

    def write_log(self, level: str, message: str, **extra: Any) -> None:
        log_file = self.project_dir / "logs" / f"{date.today().isoformat()}.jsonl"
        with open(log_file, "a") as f:
            f.write(
                json.dumps({"level": level, "message": message, "timestamp": _utc_now(), **extra}) + "\n"
            )

    # ── Component/pipeline definition storage ────────────────────────────────

    def save_component_def(self, component_id: str, definition: dict[str, Any]) -> None:
        path = self.project_dir / "components" / f"{component_id}.json"
        with open(path, "w") as f:
            json.dump(definition, f, indent=2)

    def load_component_def(self, component_id: str) -> dict[str, Any] | None:
        path = self.project_dir / "components" / f"{component_id}.json"
        if not path.exists():
            return None
        with open(path) as f:
            return json.load(f)

    def save_pipeline_def(self, pipeline_id: str, definition: dict[str, Any]) -> None:
        path = self.project_dir / "pipelines" / f"{pipeline_id}.json"
        with open(path, "w") as f:
            json.dump(definition, f, indent=2)

    def load_pipeline_def(self, pipeline_id: str) -> dict[str, Any] | None:
        path = self.project_dir / "pipelines" / f"{pipeline_id}.json"
        if not path.exists():
            return None
        with open(path) as f:
            return json.load(f)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
