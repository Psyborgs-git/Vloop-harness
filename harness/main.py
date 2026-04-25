"""Harness CLI entrypoint."""

from __future__ import annotations

import sys
import threading
import time
from typing import Literal

import typer
import uvicorn

from harness.core.main_process import MainProcess
from harness.core.service_manager import ServiceManager, ServiceStatus, ServiceTarget
from harness.server.app import create_app
from harness.settings import HarnessSettings
from harness.window import RootWindow

app = typer.Typer(name="harness", help="Vloop Harness CLI", no_args_is_help=True)
services_app = typer.Typer(help="Manage harness backend/frontend services")
internal_app = typer.Typer(help="Internal worker commands", hidden=True)
app.add_typer(services_app, name="services")
app.add_typer(internal_app, name="internal")


@app.callback()
def _callback() -> None:
    """Vloop Harness — Python brain, React face."""


def _build_fastapi_app(settings: HarnessSettings) -> "fastapi.FastAPI":  # type: ignore[name-defined]
    main_process = MainProcess(state_db=settings.state_db_path)
    return create_app(main_process=main_process, settings=settings)


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


def _print_service_status(statuses: list[ServiceStatus]) -> None:
    for status in statuses:
        marker = "healthy" if status.healthy else ("running" if status.running else "stopped")
        pid_part = f"pid={status.pid}" if status.pid else "pid=-"
        detail = f" ({status.detail})" if status.detail else ""
        typer.echo(
            f"{status.name:<8} {marker:<8} {pid_part:<12} log={status.log_path}{detail}"
        )


@app.command()
def run(
    host: str = typer.Option("localhost", envvar="HARNESS_HOST"),
    port: int = typer.Option(8000, envvar="HARNESS_PORT"),
    no_window: bool = typer.Option(
        False, help="Skip opening the native window (headless mode)"
    ),
    frontend_mode: Literal["dev", "static"] = typer.Option(
        "dev", help="Frontend mode. 'static' skips Vite dev server process."
    ),
) -> None:
    """Start the Vloop Harness orchestrator."""
    settings = HarnessSettings(harness_host=host, harness_port=port)
    manager = ServiceManager(
        settings=settings,
        backend_host=host,
        backend_port=port,
        frontend_mode=frontend_mode,
    )
    manager.cleanup_orphans()

    started_targets: list[ServiceTarget] = []

    try:
        backend_status = manager.start("backend")
        started_targets.append("backend")
        _print_service_status(backend_status)

        if frontend_mode == "dev":
            frontend_status = manager.start("frontend")
            started_targets.append("frontend")
            _print_service_status(frontend_status)
        else:
            _print_service_status(manager.status())

        root_url = f"http://{host}:{port}/ui/root"
        if not no_window:
            window = RootWindow(url=root_url)
            typer.echo(f"Opening root window → {root_url}")
            threading.Thread(target=_start_global_hotkey, args=(window,), daemon=True).start()
            window.open()  # blocks until window is closed
        else:
            typer.echo(f"Headless mode — visit {root_url} in your browser")
            typer.echo("Press Ctrl+C to stop.")
            while True:
                time.sleep(1)

    except KeyboardInterrupt:
        typer.echo("Received Ctrl+C. Shutting down services...")
    except RuntimeError as exc:
        typer.echo(f"Startup failure: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    finally:
        for target in reversed(started_targets):
            manager.stop(target)
        typer.echo("Harness stopped.")


@services_app.command("start")
def services_start(target: ServiceTarget = typer.Argument("all")) -> None:
    """Start backend/frontend services."""
    settings = HarnessSettings()
    manager = ServiceManager(settings=settings)
    manager.cleanup_orphans()
    try:
        statuses = manager.start(target)
    except RuntimeError as exc:
        typer.echo(f"Start failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    _print_service_status(statuses)


@services_app.command("stop")
def services_stop(target: ServiceTarget = typer.Argument("all")) -> None:
    """Stop backend/frontend services."""
    manager = ServiceManager(settings=HarnessSettings())
    statuses = manager.stop(target)
    _print_service_status(statuses)


@services_app.command("restart")
def services_restart(target: ServiceTarget = typer.Argument("all")) -> None:
    """Restart backend/frontend services."""
    settings = HarnessSettings()
    manager = ServiceManager(settings=settings)
    manager.cleanup_orphans()
    try:
        statuses = manager.restart(target)
    except RuntimeError as exc:
        typer.echo(f"Restart failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    _print_service_status(statuses)


@services_app.command("status")
def services_status() -> None:
    """Show backend/frontend service status."""
    manager = ServiceManager(settings=HarnessSettings())
    manager.cleanup_orphans()
    _print_service_status(manager.status())


@internal_app.command("backend-worker")
def backend_worker(
    host: str = typer.Option("localhost"),
    port: int = typer.Option(8000),
) -> None:
    """Internal command used by ServiceManager to launch uvicorn as a subprocess."""
    settings = HarnessSettings(harness_host=host, harness_port=port)
    fastapi_app = _build_fastapi_app(settings=settings)

    try:
        uvicorn.run(fastapi_app, host=host, port=port, log_level="warning")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    app()
