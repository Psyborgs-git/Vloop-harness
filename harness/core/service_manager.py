"""ServiceManager — manages harness services (backend + frontend) as named processes.

Each service can be independently started, stopped, and restarted.  The
``ServiceManager`` is attached to ``MainProcess`` so that route handlers can
query and control services at runtime via the ``/api/services`` endpoints.

Service types
─────────────
* ``UvicornService``   — FastAPI backend running in a daemon thread via
                         ``uvicorn.Server`` (stoppable via ``server.should_exit``).
* ``SubprocessService`` — Vite dev server (or any other subprocess) with an
                          optional TCP health-check gate.
"""

from __future__ import annotations

import asyncio
import subprocess
import threading
import time
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from harness.core.logger import HarnessLogger


# ── Service status ────────────────────────────────────────────────────────────


class ServiceStatus(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


# ── Base class ────────────────────────────────────────────────────────────────


class ManagedService:
    """Abstract base for a managed harness service."""

    def __init__(self, name: str, display_name: str = "") -> None:
        self.name = name
        self.display_name = display_name or name
        self._status: ServiceStatus = ServiceStatus.STOPPED
        self._error: str | None = None

    @property
    def status(self) -> ServiceStatus:
        return self._status

    @property
    def error(self) -> str | None:
        return self._error

    async def start(self) -> None:
        raise NotImplementedError

    async def stop(self) -> None:
        raise NotImplementedError

    async def restart(self) -> None:
        await self.stop()
        await self.start()

    def info(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "status": self._status.value,
            "error": self._error,
        }


# ── TCP health-check helper ───────────────────────────────────────────────────


def _wait_for_port(host: str, port: int, timeout: float = 30.0, interval: float = 0.3) -> bool:
    """Poll ``host:port`` until a TCP connection succeeds or ``timeout`` expires."""
    import socket

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(interval)
    return False


# ── Uvicorn (FastAPI backend) service ─────────────────────────────────────────


class UvicornService(ManagedService):
    """FastAPI/uvicorn backend running in a managed daemon thread.

    Uses ``uvicorn.Server`` directly so that the server can be gracefully
    stopped by setting ``server.should_exit = True``.
    """

    def __init__(
        self,
        app: Any,
        host: str,
        port: int,
        log_level: str = "warning",
        display_name: str = "",
    ) -> None:
        super().__init__("backend", display_name or "FastAPI Backend")
        self._app = app
        self._host = host
        self._port = port
        self._log_level = log_level
        self._server: Any | None = None  # uvicorn.Server
        self._thread: threading.Thread | None = None

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        return self._port

    async def start(self) -> None:
        if self._status == ServiceStatus.RUNNING:
            return
        self._status = ServiceStatus.STARTING
        self._error = None

        import uvicorn

        config = uvicorn.Config(
            self._app,
            host=self._host,
            port=self._port,
            log_level=self._log_level,
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()

        loop = asyncio.get_running_loop()
        ok = await loop.run_in_executor(
            None, lambda: _wait_for_port(self._host, self._port, timeout=15.0)
        )
        if not ok:
            self._status = ServiceStatus.ERROR
            self._error = f"Backend failed to bind on {self._host}:{self._port}"
            raise RuntimeError(self._error)
        self._status = ServiceStatus.RUNNING

    async def stop(self) -> None:
        if self._status not in (
            ServiceStatus.RUNNING,
            ServiceStatus.STARTING,
            ServiceStatus.ERROR,
        ):
            return
        self._status = ServiceStatus.STOPPING
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: self._thread.join(timeout=5))  # type: ignore[union-attr]
        self._server = None
        self._thread = None
        self._status = ServiceStatus.STOPPED

    async def restart(self) -> None:
        await self.stop()
        await self.start()

    def wait(self, timeout: float | None = None) -> None:
        """Block until the backend thread exits (or ``timeout`` seconds pass)."""
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def info(self) -> dict[str, Any]:
        base = super().info()
        base["type"] = "uvicorn"
        base["host"] = self._host
        base["port"] = self._port
        base["url"] = f"http://{self._host}:{self._port}"
        return base


# ── Subprocess (Vite / any CLI) service ──────────────────────────────────────


class SubprocessService(ManagedService):
    """Service backed by an OS subprocess (e.g., Vite dev server).

    An optional TCP health-check gate is polled after the subprocess starts;
    if the port does not become reachable within ``health_timeout`` seconds the
    subprocess is killed and a ``RuntimeError`` is raised.
    """

    def __init__(
        self,
        name: str,
        cmd: list[str],
        cwd: str | None = None,
        health_check: tuple[str, int] | None = None,
        health_timeout: float = 30.0,
        env: dict[str, str] | None = None,
        display_name: str = "",
    ) -> None:
        super().__init__(name, display_name)
        self._cmd = cmd
        self._cwd = cwd
        self._health_check = health_check
        self._health_timeout = health_timeout
        self._env = env
        self._proc: subprocess.Popen[bytes] | None = None

    @property
    def pid(self) -> int | None:
        return self._proc.pid if self._proc else None

    async def start(self) -> None:
        if self._status == ServiceStatus.RUNNING:
            return
        self._status = ServiceStatus.STARTING
        self._error = None
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, self._do_start)
        except Exception as exc:
            self._status = ServiceStatus.ERROR
            self._error = str(exc)
            raise

    def _do_start(self) -> None:
        import os

        env = None
        if self._env:
            env = {**os.environ, **self._env}
        self._proc = subprocess.Popen(
            self._cmd,
            cwd=self._cwd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            env=env,
        )
        if self._health_check:
            host, port = self._health_check
            if not _wait_for_port(host, port, timeout=self._health_timeout):
                stderr_out = b""
                try:
                    self._proc.kill()
                    stderr_out = self._proc.stderr.read() if self._proc.stderr else b""
                except Exception:
                    pass
                self._proc = None
                raise RuntimeError(
                    f"Service '{self.name}' failed to start "
                    f"(port {host}:{port} not reachable).\n"
                    + stderr_out.decode(errors="replace")
                )
        self._status = ServiceStatus.RUNNING

    async def stop(self) -> None:
        if self._status not in (
            ServiceStatus.RUNNING,
            ServiceStatus.STARTING,
            ServiceStatus.ERROR,
        ):
            return
        self._status = ServiceStatus.STOPPING
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._do_stop)
        self._status = ServiceStatus.STOPPED

    def _do_stop(self) -> None:
        if self._proc is None:
            return
        try:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait()
        except Exception:
            pass
        finally:
            self._proc = None

    def info(self) -> dict[str, Any]:
        base = super().info()
        base["type"] = "subprocess"
        base["pid"] = self.pid
        if self._health_check:
            host, port = self._health_check
            base["url"] = f"http://{host}:{port}"
        return base


# ── Service manager ───────────────────────────────────────────────────────────


class ServiceManager:
    """Manages a collection of named harness services.

    Services are registered by name and can be individually started, stopped,
    and restarted.  ``start_all`` / ``stop_all`` operate in registration order
    (reversed for stop so that the frontend stops before the backend).
    """

    def __init__(self, logger: "HarnessLogger | None" = None) -> None:
        self._services: dict[str, ManagedService] = {}
        self._log = logger

    # ── Registration ──────────────────────────────────────────────────────────

    def register(self, service: ManagedService) -> None:
        self._services[service.name] = service

    def get(self, name: str) -> ManagedService | None:
        return self._services.get(name)

    def list_all(self) -> list[ManagedService]:
        return list(self._services.values())

    # ── Bulk lifecycle ────────────────────────────────────────────────────────

    async def start_all(self) -> None:
        for service in self._services.values():
            try:
                await service.start()
                if self._log:
                    self._log.info(f"Service '{service.name}' started", service=service.name)
            except Exception as exc:
                if self._log:
                    self._log.error(
                        f"Service '{service.name}' failed to start: {exc}",
                        service=service.name,
                    )
                raise

    async def stop_all(self) -> None:
        for service in reversed(list(self._services.values())):
            try:
                await service.stop()
                if self._log:
                    self._log.info(f"Service '{service.name}' stopped", service=service.name)
            except Exception as exc:
                if self._log:
                    self._log.error(
                        f"Service '{service.name}' failed to stop cleanly: {exc}",
                        service=service.name,
                    )
