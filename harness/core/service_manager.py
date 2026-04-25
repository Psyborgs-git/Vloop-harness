"""Service-oriented process manager for harness backend/frontend services."""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from harness.settings import HarnessSettings

ServiceName = Literal["backend", "frontend"]
ServiceTarget = Literal["backend", "frontend", "all"]


@dataclass(slots=True)
class ServiceStatus:
    name: ServiceName
    running: bool
    healthy: bool
    pid: int | None
    log_path: Path
    detail: str = ""


class ServiceManager:
    """Starts/stops backend and frontend services as subprocesses."""

    def __init__(
        self,
        settings: HarnessSettings,
        backend_host: str | None = None,
        backend_port: int | None = None,
        frontend_mode: Literal["dev", "static"] = "dev",
    ) -> None:
        self.settings = settings
        self.backend_host = backend_host or settings.harness_host
        self.backend_port = backend_port or settings.harness_port
        self.frontend_mode = frontend_mode
        self.repo_root = Path(__file__).resolve().parents[2]

        self.log_dir = Path(settings.log_dir)
        self.service_dir = self.log_dir / "services"
        self.service_dir.mkdir(parents=True, exist_ok=True)

    # ── Public API ──────────────────────────────────────────────────────────

    def start(self, target: ServiceTarget) -> list[ServiceStatus]:
        targets = self._expand_target(target)
        statuses: list[ServiceStatus] = []
        for name in targets:
            if name == "backend":
                statuses.append(self._start_backend())
            elif name == "frontend":
                statuses.append(self._start_frontend())
        return statuses

    def stop(self, target: ServiceTarget) -> list[ServiceStatus]:
        targets = self._expand_target(target)
        statuses: list[ServiceStatus] = []
        for name in targets:
            statuses.append(self._stop_service(name))
        return statuses

    def restart(self, target: ServiceTarget) -> list[ServiceStatus]:
        self.stop(target)
        return self.start(target)

    def status(self) -> list[ServiceStatus]:
        statuses: list[ServiceStatus] = []
        for name in ("backend", "frontend"):
            if name == "frontend" and self.frontend_mode == "static":
                statuses.append(
                    ServiceStatus(
                        name="frontend",
                        running=False,
                        healthy=True,
                        pid=None,
                        log_path=self._service_log("frontend"),
                        detail="static mode (no frontend process)",
                    )
                )
                continue
            statuses.append(self._status_for(name))
        return statuses

    def cleanup_orphans(self) -> None:
        """Remove stale PID files left behind by crashed processes."""
        for name in ("backend", "frontend"):
            pid = self._read_pid(name)
            if pid is not None and not self._pid_alive(pid):
                self._pid_file(name).unlink(missing_ok=True)

    # ── Start helpers ────────────────────────────────────────────────────────

    def _start_backend(self) -> ServiceStatus:
        status = self._status_for("backend")
        if status.running and status.healthy:
            status.detail = f"already running on http://{self.backend_host}:{self.backend_port}"
            return status

        if self._port_in_use(self.backend_host, self.backend_port):
            raise RuntimeError(
                f"Backend port conflict on {self.backend_host}:{self.backend_port}. "
                "Stop the conflicting process or set HARNESS_PORT to a free port."
            )

        cmd = [
            sys.executable,
            "-m",
            "harness.main",
            "internal",
            "backend-worker",
            "--host",
            self.backend_host,
            "--port",
            str(self.backend_port),
        ]
        proc = self._spawn_service(
            "backend",
            cmd,
            cwd=self.repo_root,
            env_overrides={"HARNESS_DEBUG": "false" if self.frontend_mode == "static" else "true"},
        )

        if not self._wait_for_port(self.backend_host, self.backend_port, timeout=20.0):
            err = self._read_log_tail("backend")
            self._terminate_pid(proc.pid)
            raise RuntimeError(
                "Backend failed to start. "
                f"Log tail from {self._service_log('backend')}:\n{err}"
            )

        return self._status_for("backend")

    def _start_frontend(self) -> ServiceStatus:
        if self.frontend_mode == "static":
            return ServiceStatus(
                name="frontend",
                running=False,
                healthy=True,
                pid=None,
                log_path=self._service_log("frontend"),
                detail="static mode (no frontend process)",
            )

        status = self._status_for("frontend")
        if status.running and status.healthy:
            status.detail = f"already running on http://{self.settings.vite_host}:{self.settings.vite_port}"
            return status

        react_dir = self.repo_root / "react"
        if not react_dir.exists():
            raise RuntimeError("Frontend directory 'react/' was not found.")
        if not (react_dir / "node_modules").exists():
            raise RuntimeError(
                "Frontend dependencies are missing. Run: cd react && npm install"
            )
        if self._which("npm") is None:
            raise RuntimeError("npm was not found on PATH. Install Node.js and npm first.")

        if self._port_in_use(self.settings.vite_host, self.settings.vite_port):
            raise RuntimeError(
                f"Frontend port conflict on {self.settings.vite_host}:{self.settings.vite_port}. "
                "Stop the conflicting process or set VITE_PORT to a free port."
            )

        cmd = [
            "npm",
            "run",
            "dev",
            "--",
            "--port",
            str(self.settings.vite_port),
            "--host",
        ]
        proc = self._spawn_service("frontend", cmd, cwd=react_dir)

        if not self._wait_for_port(self.settings.vite_host, self.settings.vite_port, timeout=30.0):
            err = self._read_log_tail("frontend")
            self._terminate_pid(proc.pid)
            raise RuntimeError(
                "Frontend failed to start. "
                f"Check node_modules and Vite config. Log tail from {self._service_log('frontend')}:\n{err}"
            )

        return self._status_for("frontend")

    # ── Stop/status helpers ──────────────────────────────────────────────────

    def _stop_service(self, name: ServiceName) -> ServiceStatus:
        pid = self._read_pid(name)
        if pid is None:
            return ServiceStatus(
                name=name,
                running=False,
                healthy=False,
                pid=None,
                log_path=self._service_log(name),
                detail="not running",
            )

        self._terminate_pid(pid)
        self._pid_file(name).unlink(missing_ok=True)

        status = self._status_for(name)
        status.detail = "stopped"
        return status

    def _status_for(self, name: ServiceName) -> ServiceStatus:
        pid = self._read_pid(name)
        running = pid is not None and self._pid_alive(pid)
        healthy = running and self._health_check(name)
        detail = ""

        if pid is None:
            detail = "not started"
        elif not running:
            detail = "stale pid"
        elif not healthy:
            detail = "running but unhealthy"

        return ServiceStatus(
            name=name,
            running=running,
            healthy=healthy,
            pid=pid,
            log_path=self._service_log(name),
            detail=detail,
        )

    # ── Health/PID helpers ───────────────────────────────────────────────────

    def _health_check(self, name: ServiceName) -> bool:
        if name == "backend":
            return self._wait_for_port(self.backend_host, self.backend_port, timeout=0.5, interval=0.1)
        return self._wait_for_port(
            self.settings.vite_host,
            self.settings.vite_port,
            timeout=0.5,
            interval=0.1,
        )

    def _write_pid(self, name: ServiceName, pid: int, command: list[str], cwd: Path) -> None:
        payload = {
            "pid": pid,
            "command": command,
            "cwd": str(cwd),
            "started_at": time.time(),
        }
        self._pid_file(name).write_text(json.dumps(payload), encoding="utf-8")

    def _read_pid(self, name: ServiceName) -> int | None:
        path = self._pid_file(name)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            value = data.get("pid")
            return int(value) if value is not None else None
        except Exception:
            return None

    def _pid_alive(self, pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    # ── Process utilities ────────────────────────────────────────────────────

    def _spawn_service(
        self,
        name: ServiceName,
        cmd: list[str],
        cwd: Path,
        env_overrides: dict[str, str] | None = None,
    ) -> subprocess.Popen[bytes]:
        log_file = self._service_log(name)
        env = os.environ.copy()
        if env_overrides:
            env.update(env_overrides)
        with log_file.open("ab") as log:
            proc = subprocess.Popen(
                cmd,
                cwd=str(cwd),
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                env=env,
            )
        self._write_pid(name, proc.pid, cmd, cwd)
        return proc

    def _terminate_pid(self, pid: int) -> None:
        if not self._pid_alive(pid):
            return

        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGTERM)
        except Exception:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                return

        deadline = time.time() + 10
        while time.time() < deadline:
            if not self._pid_alive(pid):
                return
            time.sleep(0.2)

        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGKILL)
        except Exception:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass

    def _service_log(self, name: ServiceName) -> Path:
        return self.service_dir / f"{name}.log"

    def _pid_file(self, name: ServiceName) -> Path:
        return self.service_dir / f"{name}.pid"

    def _read_log_tail(self, name: ServiceName, max_bytes: int = 8000) -> str:
        path = self._service_log(name)
        if not path.exists():
            return "<no log output>"
        data = path.read_bytes()
        return data[-max_bytes:].decode(errors="replace")

    @staticmethod
    def _wait_for_port(
        host: str,
        port: int,
        timeout: float = 30.0,
        interval: float = 0.3,
    ) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with socket.create_connection((host, port), timeout=0.5):
                    return True
            except OSError:
                time.sleep(interval)
        return False

    @staticmethod
    def _port_in_use(host: str, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
            except OSError:
                return True
        return False

    @staticmethod
    def _which(binary: str) -> str | None:
        for path in os.environ.get("PATH", "").split(os.pathsep):
            candidate = Path(path) / binary
            if candidate.exists() and os.access(candidate, os.X_OK):
                return str(candidate)
        return None

    @staticmethod
    def _expand_target(target: ServiceTarget) -> list[ServiceName]:
        if target == "all":
            return ["backend", "frontend"]
        return [target]
