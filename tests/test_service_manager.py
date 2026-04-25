from __future__ import annotations

import json

from harness.core.service_manager import ServiceManager
from harness.settings import HarnessSettings


def _manager(tmp_path, frontend_mode: str = "dev") -> ServiceManager:
    settings = HarnessSettings(
        log_dir=str(tmp_path / "logs"),
        harness_host="127.0.0.1",
        harness_port=18000,
        vite_host="127.0.0.1",
        vite_port=15173,
    )
    return ServiceManager(settings=settings, frontend_mode=frontend_mode)  # type: ignore[arg-type]


def test_expand_target() -> None:
    assert ServiceManager._expand_target("all") == ["backend", "frontend"]
    assert ServiceManager._expand_target("backend") == ["backend"]


def test_status_static_frontend(tmp_path) -> None:
    manager = _manager(tmp_path, frontend_mode="static")
    statuses = manager.status()
    frontend = next(item for item in statuses if item.name == "frontend")

    assert frontend.healthy is True
    assert frontend.running is False
    assert "static mode" in frontend.detail


def test_cleanup_orphans_removes_stale_pid(tmp_path) -> None:
    manager = _manager(tmp_path)
    pid_path = manager._pid_file("backend")
    pid_path.write_text(json.dumps({"pid": 999999}), encoding="utf-8")

    manager.cleanup_orphans()

    assert not pid_path.exists()
