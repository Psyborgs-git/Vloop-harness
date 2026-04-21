"""Unit tests for VLoopStorage — JSONL helpers, archive, telemetry, logging.

Tests use a temporary directory so no real ~/.vloop or .vloop directories
are touched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.vloop.storage import VLoopStorage


@pytest.fixture
def storage(tmp_path: Path) -> VLoopStorage:
    """Return a VLoopStorage rooted at a temporary directory."""
    return VLoopStorage(cwd=tmp_path)


# ── Chat JSONL helpers ─────────────────────────────────────────────────────────


class TestChatJsonl:
    def test_append_creates_file(self, storage: VLoopStorage) -> None:
        storage.append_chat_message("sess1", {"id": "m1", "role": "user", "content": "hi"})
        assert storage.chat_session_file("sess1").exists()

    def test_append_single_line_readable(self, storage: VLoopStorage) -> None:
        msg = {"id": "m1", "session_id": "sess1", "role": "user", "content": "hello", "v": 1}
        storage.append_chat_message("sess1", msg)
        lines = storage.read_chat_session("sess1")
        assert len(lines) == 1
        assert lines[0]["id"] == "m1"
        assert lines[0]["role"] == "user"

    def test_append_multiple_messages(self, storage: VLoopStorage) -> None:
        for i in range(5):
            storage.append_chat_message("sess2", {"id": f"m{i}", "content": f"msg{i}"})
        lines = storage.read_chat_session("sess2")
        assert len(lines) == 5

    def test_read_missing_session_returns_empty(self, storage: VLoopStorage) -> None:
        result = storage.read_chat_session("does_not_exist")
        assert result == []

    def test_append_timestamp_added(self, storage: VLoopStorage) -> None:
        storage.append_chat_message("sess3", {"id": "m1"})
        lines = storage.read_chat_session("sess3")
        assert "timestamp" in lines[0]

    def test_each_line_is_valid_json(self, storage: VLoopStorage) -> None:
        for i in range(3):
            storage.append_chat_message("sess4", {"id": f"m{i}", "content": "x"})
        raw_path = storage.chat_session_file("sess4")
        for line in raw_path.read_text().splitlines():
            obj = json.loads(line)  # must not raise
            assert isinstance(obj, dict)

    def test_jsonl_format_has_one_json_per_line(self, storage: VLoopStorage) -> None:
        storage.append_chat_message("sess5", {"a": 1})
        storage.append_chat_message("sess5", {"b": 2})
        raw = storage.chat_session_file("sess5").read_text()
        lines = [l for l in raw.splitlines() if l.strip()]
        assert len(lines) == 2
        assert json.loads(lines[0])["a"] == 1
        assert json.loads(lines[1])["b"] == 2


# ── archive_chat_session ───────────────────────────────────────────────────────


class TestArchiveChatSession:
    def test_renames_file_to_deleted(self, storage: VLoopStorage) -> None:
        storage.append_chat_message("sess_del", {"id": "m1"})
        src = storage.chat_session_file("sess_del")
        assert src.exists()
        storage.archive_chat_session("sess_del")
        assert not src.exists()
        deleted = src.parent / (src.name + ".deleted")
        assert deleted.exists()

    def test_archive_nonexistent_is_safe(self, storage: VLoopStorage) -> None:
        # Should not raise even if the file never existed
        storage.archive_chat_session("never_existed")

    def test_archived_content_preserved(self, storage: VLoopStorage) -> None:
        storage.append_chat_message("sess_arc", {"content": "preserved"})
        storage.archive_chat_session("sess_arc")
        archived = storage.chat_session_file("sess_arc").parent / "sess_arc.jsonl.deleted"
        data = json.loads(archived.read_text().splitlines()[0])
        assert data["content"] == "preserved"

    def test_archive_twice_no_error(self, storage: VLoopStorage) -> None:
        storage.append_chat_message("sess_dbl", {"id": "m1"})
        storage.archive_chat_session("sess_dbl")
        # Calling again should not raise (file already gone)
        storage.archive_chat_session("sess_dbl")


# ── Telemetry ──────────────────────────────────────────────────────────────────


class TestTelemetry:
    def test_log_telemetry_creates_daily_file(self, storage: VLoopStorage) -> None:
        from datetime import date

        storage.log_telemetry("test_event", {"key": "value"})
        today = date.today().isoformat()
        tel_file = storage.project_dir / "telemetry" / f"{today}.jsonl"
        assert tel_file.exists()

    def test_log_telemetry_content_readable(self, storage: VLoopStorage) -> None:
        storage.log_telemetry("chat_message", {"session_id": "s1"})
        from datetime import date

        today = date.today().isoformat()
        tel_file = storage.project_dir / "telemetry" / f"{today}.jsonl"
        lines = [json.loads(l) for l in tel_file.read_text().splitlines() if l.strip()]
        assert any(e["type"] == "chat_message" for e in lines)

    def test_multiple_events_appended(self, storage: VLoopStorage) -> None:
        storage.log_telemetry("event_a", {})
        storage.log_telemetry("event_b", {})
        from datetime import date

        today = date.today().isoformat()
        tel_file = storage.project_dir / "telemetry" / f"{today}.jsonl"
        lines = [json.loads(l) for l in tel_file.read_text().splitlines() if l.strip()]
        types = [e["type"] for e in lines]
        assert "event_a" in types
        assert "event_b" in types


# ── Structured log ─────────────────────────────────────────────────────────────


class TestWriteLog:
    def test_write_log_creates_daily_file(self, storage: VLoopStorage) -> None:
        from datetime import date

        storage.write_log("info", "test started")
        today = date.today().isoformat()
        log_file = storage.project_dir / "logs" / f"{today}.jsonl"
        assert log_file.exists()

    def test_write_log_content(self, storage: VLoopStorage) -> None:
        storage.write_log("error", "something broke", extra="data")
        from datetime import date

        today = date.today().isoformat()
        log_file = storage.project_dir / "logs" / f"{today}.jsonl"
        lines = [json.loads(l) for l in log_file.read_text().splitlines() if l.strip()]
        assert lines[-1]["level"] == "error"
        assert lines[-1]["message"] == "something broke"

    def test_write_log_extra_fields(self, storage: VLoopStorage) -> None:
        storage.write_log("info", "startup", db_url="sqlite:///test.db")
        from datetime import date

        today = date.today().isoformat()
        log_file = storage.project_dir / "logs" / f"{today}.jsonl"
        lines = [json.loads(l) for l in log_file.read_text().splitlines() if l.strip()]
        assert lines[-1].get("db_url") == "sqlite:///test.db"


# ── Component / pipeline definition storage ────────────────────────────────────


class TestComponentPipelineStorage:
    def test_save_and_load_component_def(self, storage: VLoopStorage) -> None:
        defn = {"id": "comp_1", "name": "MyComp", "code": "class Foo: pass"}
        storage.save_component_def("comp_1", defn)
        loaded = storage.load_component_def("comp_1")
        assert loaded == defn

    def test_load_missing_component_returns_none(self, storage: VLoopStorage) -> None:
        assert storage.load_component_def("nonexistent") is None

    def test_save_and_load_pipeline_def(self, storage: VLoopStorage) -> None:
        defn = {"id": "pipe_1", "name": "Pipeline", "steps": []}
        storage.save_pipeline_def("pipe_1", defn)
        loaded = storage.load_pipeline_def("pipe_1")
        assert loaded == defn

    def test_load_missing_pipeline_returns_none(self, storage: VLoopStorage) -> None:
        assert storage.load_pipeline_def("missing") is None

    def test_overwrite_component_def(self, storage: VLoopStorage) -> None:
        storage.save_component_def("c1", {"version": 1})
        storage.save_component_def("c1", {"version": 2})
        assert storage.load_component_def("c1") == {"version": 2}


# ── Global settings ────────────────────────────────────────────────────────────


class TestGlobalSettings:
    def test_load_returns_empty_if_no_file(self, storage: VLoopStorage) -> None:
        # Ensure settings file doesn't exist
        if storage.global_settings_path.exists():
            storage.global_settings_path.unlink()
        result = storage.load_global_settings()
        assert result == {}

    def test_save_and_load_settings(self, storage: VLoopStorage) -> None:
        settings = {"theme": "dark", "language": "en"}
        storage.save_global_settings(settings)
        loaded = storage.load_global_settings()
        assert loaded == settings

    def test_overwrite_settings(self, storage: VLoopStorage) -> None:
        storage.save_global_settings({"a": 1})
        storage.save_global_settings({"b": 2})
        assert storage.load_global_settings() == {"b": 2}
