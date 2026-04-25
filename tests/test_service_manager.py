"""Unit tests for harness.core.service_manager.

Tests cover:
- ServiceStatus enum values
- ManagedService base class defaults
- SubprocessService start/stop/restart/info with a trivial echo command
- UvicornService info() shape without actually starting uvicorn
- ServiceManager register/get/list_all/start_all/stop_all
- _wait_for_port helper (fast path — already-open port)
"""

from __future__ import annotations

import asyncio
import socket
import threading
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from harness.core.service_manager import (
    ManagedService,
    ServiceManager,
    ServiceStatus,
    SubprocessService,
    UvicornService,
    _wait_for_port,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


class _SimpleService(ManagedService):
    """Minimal concrete service for testing the base class."""

    def __init__(self) -> None:
        super().__init__("simple", "Simple Test Service")
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self._status = ServiceStatus.RUNNING
        self.started = True

    async def stop(self) -> None:
        self._status = ServiceStatus.STOPPED
        self.stopped = True


# ── ServiceStatus ─────────────────────────────────────────────────────────────


def test_service_status_values() -> None:
    assert ServiceStatus.STOPPED == "stopped"
    assert ServiceStatus.STARTING == "starting"
    assert ServiceStatus.RUNNING == "running"
    assert ServiceStatus.STOPPING == "stopping"
    assert ServiceStatus.ERROR == "error"


# ── ManagedService base ───────────────────────────────────────────────────────


def test_managed_service_defaults() -> None:
    svc = _SimpleService()
    assert svc.name == "simple"
    assert svc.display_name == "Simple Test Service"
    assert svc.status == ServiceStatus.STOPPED
    assert svc.error is None


@pytest.mark.asyncio
async def test_managed_service_restart() -> None:
    svc = _SimpleService()
    await svc.start()
    assert svc.status == ServiceStatus.RUNNING
    await svc.restart()
    assert svc.started is True
    assert svc.stopped is True
    assert svc.status == ServiceStatus.RUNNING


def test_managed_service_info() -> None:
    svc = _SimpleService()
    info = svc.info()
    assert info["name"] == "simple"
    assert info["display_name"] == "Simple Test Service"
    assert info["status"] == "stopped"
    assert info["error"] is None


# ── _wait_for_port ────────────────────────────────────────────────────────────


def test_wait_for_port_succeeds_on_open_port() -> None:
    """Open a real server socket, then verify _wait_for_port returns True."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        _, port = srv.getsockname()
        assert _wait_for_port("127.0.0.1", port, timeout=2.0) is True


def test_wait_for_port_times_out_on_closed_port() -> None:
    # Use a port that nothing is listening on; very short timeout
    assert _wait_for_port("127.0.0.1", 1, timeout=0.3) is False


# ── SubprocessService ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_subprocess_service_start_stop(tmp_path: Any) -> None:
    """Start a subprocess that sleeps briefly, verify it can be stopped."""
    svc = SubprocessService(
        name="test_proc",
        cmd=["python", "-c", "import time; time.sleep(30)"],
        health_check=None,
    )
    await svc.start()
    assert svc.status == ServiceStatus.RUNNING
    assert svc.pid is not None

    await svc.stop()
    assert svc.status == ServiceStatus.STOPPED
    assert svc.pid is None


@pytest.mark.asyncio
async def test_subprocess_service_info() -> None:
    svc = SubprocessService(
        name="proc_info",
        cmd=["python", "-c", "pass"],
        health_check=None,
        display_name="Proc Info Service",
    )
    await svc.start()
    info = svc.info()
    assert info["name"] == "proc_info"
    assert info["type"] == "subprocess"
    assert info["status"] in ("running", "stopped")  # quick command may finish
    await svc.stop()


@pytest.mark.asyncio
async def test_subprocess_service_start_idempotent() -> None:
    svc = SubprocessService(
        name="idem",
        cmd=["python", "-c", "import time; time.sleep(30)"],
        health_check=None,
    )
    await svc.start()
    pid_first = svc.pid
    await svc.start()  # second call — should be a no-op
    assert svc.pid == pid_first
    await svc.stop()


@pytest.mark.asyncio
async def test_subprocess_service_health_check_failure() -> None:
    """Health check pointing to a port nobody is listening on should raise."""
    svc = SubprocessService(
        name="bad_health",
        cmd=["python", "-c", "import time; time.sleep(30)"],
        health_check=("127.0.0.1", 1),  # port 1 is always closed
        health_timeout=0.3,
    )
    with pytest.raises(RuntimeError, match="not reachable"):
        await svc.start()
    assert svc.status == ServiceStatus.ERROR


# ── UvicornService (info / shape tests without actual binding) ────────────────


def test_uvicorn_service_initial_state() -> None:
    svc = UvicornService(app=MagicMock(), host="127.0.0.1", port=19876)
    assert svc.name == "backend"
    assert svc.status == ServiceStatus.STOPPED
    assert svc.host == "127.0.0.1"
    assert svc.port == 19876


def test_uvicorn_service_info_shape() -> None:
    svc = UvicornService(app=MagicMock(), host="0.0.0.0", port=8001, display_name="My API")
    info = svc.info()
    assert info["type"] == "uvicorn"
    assert info["host"] == "0.0.0.0"
    assert info["port"] == 8001
    assert info["url"] == "http://0.0.0.0:8001"
    assert info["display_name"] == "My API"


@pytest.mark.asyncio
async def test_uvicorn_service_stop_when_not_running() -> None:
    """stop() on a not-started service should be a no-op."""
    svc = UvicornService(app=MagicMock(), host="127.0.0.1", port=19877)
    await svc.stop()  # should not raise
    assert svc.status == ServiceStatus.STOPPED


# ── ServiceManager ────────────────────────────────────────────────────────────


def test_service_manager_register_and_get() -> None:
    sm = ServiceManager()
    svc = _SimpleService()
    sm.register(svc)
    assert sm.get("simple") is svc
    assert sm.get("nonexistent") is None


def test_service_manager_list_all() -> None:
    sm = ServiceManager()
    svc1 = _SimpleService()
    svc2 = _SimpleService()
    svc2.name = "other"
    sm.register(svc1)
    sm.register(svc2)
    names = [s.name for s in sm.list_all()]
    assert "simple" in names
    assert "other" in names


@pytest.mark.asyncio
async def test_service_manager_start_all() -> None:
    sm = ServiceManager()
    s1 = _SimpleService()
    s2 = _SimpleService()
    s2.name = "s2"
    sm.register(s1)
    sm.register(s2)
    await sm.start_all()
    assert s1.status == ServiceStatus.RUNNING
    assert s2.status == ServiceStatus.RUNNING


@pytest.mark.asyncio
async def test_service_manager_stop_all() -> None:
    sm = ServiceManager()
    s1 = _SimpleService()
    sm.register(s1)
    await sm.start_all()
    await sm.stop_all()
    assert s1.status == ServiceStatus.STOPPED


@pytest.mark.asyncio
async def test_service_manager_start_all_propagates_error() -> None:
    class _FailService(ManagedService):
        async def start(self) -> None:
            self._status = ServiceStatus.ERROR
            raise RuntimeError("boom")

        async def stop(self) -> None:
            pass

    sm = ServiceManager()
    sm.register(_FailService("fail"))
    with pytest.raises(RuntimeError, match="boom"):
        await sm.start_all()


@pytest.mark.asyncio
async def test_service_manager_logs_on_start(capsys: Any) -> None:
    """When a logger is provided, start/stop log messages are emitted."""
    mock_logger = MagicMock()
    mock_logger.info = MagicMock()

    sm = ServiceManager(logger=mock_logger)
    svc = _SimpleService()
    sm.register(svc)
    await sm.start_all()
    mock_logger.info.assert_called()
