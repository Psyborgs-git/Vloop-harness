"""
Harness entrypoint.

Boot sequence:
  1. Load settings
  2. Configure AI engine (DSPy)
  3. Build MainProcess
  4. Create FastAPI app
  5. Build ServiceManager with backend (UvicornService) and optional
     frontend (SubprocessService for Vite dev server)
  6. Start all services via ServiceManager
  7. Attach ServiceManager to MainProcess so API routes can query/control it
  8. Open PyWebView root window (blocks until closed)
"""

from __future__ import annotations

import asyncio
import socket
import sys
import time
import threading
from pathlib import Path

import typer

from harness.core.main_process import MainProcess
from harness.core.service_manager import ServiceManager, SubprocessService, UvicornService
from harness.engine.config import EngineConfig
from harness.engine.dspy_engine import DSPyEngine
from harness.server.app import create_app
from harness.settings import HarnessSettings
from harness.window import RootWindow

app = typer.Typer(name="harness", help="Vloop Harness CLI", no_args_is_help=True)


@app.callback()
def _callback() -> None:
    """Vloop Harness — Python brain, React face."""


def _wait_for_port(host: str, port: int, timeout: float = 30.0, interval: float = 0.3) -> bool:
    """Poll host:port until TCP connect succeeds or timeout expires."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(interval)
    return False


def _start_global_hotkey(window: "RootWindow") -> None:
    """Daemon thread: double-tap Cmd brings the PyWebView window to front."""
    try:
        from pynput import keyboard as kb
    except ImportError:
        return  # pynput not installed — skip silently

    last_cmd_time = 0.0
    DOUBLE_TAP_S = 0.4

    def on_press(key: "kb.Key") -> None:
        nonlocal last_cmd_time
        if key in (kb.Key.cmd, kb.Key.cmd_l, kb.Key.cmd_r):
            now = time.time()
            if now - last_cmd_time < DOUBLE_TAP_S:
                window.focus()
                last_cmd_time = 0.0
            else:
                last_cmd_time = now

    listener = kb.Listener(on_press=on_press)
    listener.daemon = True
    listener.start()
    listener.join()


@app.command()
def run(
    host: str = typer.Option("localhost", envvar="HARNESS_HOST"),
    port: int = typer.Option(8000, envvar="HARNESS_PORT"),
    no_window: bool = typer.Option(
        False, help="Skip opening the native window (headless mode)"
    ),
    no_ai: bool = typer.Option(False, help="Skip AI engine initialisation"),
    no_vite: bool = typer.Option(False, help="Skip starting the Vite dev server"),
) -> None:
    """Start the Vloop Harness."""
    settings = HarnessSettings()
    main_process = MainProcess(state_db=settings.state_db_path)

    # ── AI engine ─────────────────────────────────────────────────────────────
    if not no_ai:
        engine_cfg = EngineConfig()
        engine = DSPyEngine(config=engine_cfg)
        try:
            engine.configure()
            main_process.attach_ai_engine(engine)
            typer.echo(f"AI engine ready: {engine}")
        except Exception as exc:
            typer.echo(
                f"Warning: AI engine failed to configure ({exc}). Running without AI.",
                err=True,
            )

    # ── FastAPI app ────────────────────────────────────────────────────────────
    fastapi_app = create_app(main_process=main_process, settings=settings)

    # ── Service manager ────────────────────────────────────────────────────────
    service_manager = ServiceManager(logger=main_process.logger)

    # Backend: FastAPI/uvicorn running in a daemon thread
    backend_service = UvicornService(
        app=fastapi_app,
        host=host,
        port=port,
        display_name="FastAPI Backend",
    )
    service_manager.register(backend_service)

    # Frontend: Vite dev server subprocess (optional)
    react_dir = Path(__file__).parent.parent / "react"
    if not no_vite and react_dir.exists():
        frontend_service = SubprocessService(
            name="frontend",
            display_name="React Dev Server (Vite)",
            cmd=["npm", "run", "dev", "--", "--port", str(settings.vite_port), "--host"],
            cwd=str(react_dir),
            health_check=(settings.vite_host, settings.vite_port),
            health_timeout=30.0,
        )
        service_manager.register(frontend_service)

    # Start all services synchronously (run the async start_all on a new loop)
    async def _start_services() -> None:
        await service_manager.start_all()

    try:
        asyncio.run(_start_services())
    except Exception as exc:
        typer.echo(f"Error: failed to start services — {exc}", err=True)
        sys.exit(1)

    typer.echo(f"API server ready on http://{host}:{port}")

    if not no_vite and react_dir.exists() and service_manager.get("frontend"):
        frontend = service_manager.get("frontend")
        if frontend and frontend.status.value == "running":
            typer.echo(
                f"Vite dev server started on "
                f"http://{settings.vite_host}:{settings.vite_port}"
            )

    # Attach ServiceManager to MainProcess so route handlers can use it
    main_process.attach_service_manager(service_manager)

    # ── Root window ───────────────────────────────────────────────────────────
    root_url = f"http://{host}:{port}/ui/root"
    if not no_window:
        window = RootWindow(url=root_url)
        typer.echo(f"Opening root window → {root_url}")
        # Global double-Cmd hotkey — runs in its own daemon thread
        threading.Thread(target=_start_global_hotkey, args=(window,), daemon=True).start()
        window.open()  # blocks until window is closed
    else:
        typer.echo(f"Headless mode — visit {root_url} in your browser")
        typer.echo("Press Ctrl+C to stop.")
        try:
            # Keep the main thread alive; backend runs on its daemon thread
            backend_service._thread.join()  # type: ignore[union-attr]
        except KeyboardInterrupt:
            pass

    # ── Cleanup ───────────────────────────────────────────────────────────────
    async def _stop_services() -> None:
        await service_manager.stop_all()

    asyncio.run(_stop_services())
    typer.echo("Harness stopped.")


if __name__ == "__main__":
    app()

