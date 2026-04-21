"""
Harness entrypoint.

Boot sequence:
  1. Load settings
  2. Configure AI engine (DSPy)
  3. Build MainProcess
  4. Create FastAPI app
  5. Start Vite dev server subprocess
  6. Start uvicorn on background thread
  7. Open PyWebView root window (blocks until closed)
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import threading
import time
from pathlib import Path

import typer
import uvicorn

from harness.core.main_process import MainProcess
from harness.engine.config import EngineConfig
from harness.engine.dspy_engine import DSPyEngine
from harness.server.app import create_app
from harness.settings import HarnessSettings
from harness.window import RootWindow

app = typer.Typer(name="harness", help="Vloop Harness CLI", no_args_is_help=True)


@app.callback()
def _callback() -> None:
    """Vloop Harness — Python brain, React face."""


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


def _start_vite(vite_port: int, react_dir: Path) -> subprocess.Popen[bytes]:
    cmd = ["npm", "run", "dev", "--", "--port", str(vite_port), "--host"]
    proc = subprocess.Popen(
        cmd,
        cwd=str(react_dir),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Give Vite a moment to bind
    time.sleep(2)
    return proc


def _run_uvicorn(fastapi_app: "fastapi.FastAPI", host: str, port: int) -> None:  # type: ignore[name-defined]
    uvicorn.run(fastapi_app, host=host, port=port, log_level="info")


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

    # ── FastAPI ───────────────────────────────────────────────────────────────
    fastapi_app = create_app(main_process=main_process, settings=settings)

    server_thread = threading.Thread(
        target=_run_uvicorn,
        args=(fastapi_app, host, port),
        daemon=True,
    )
    server_thread.start()
    typer.echo(f"API server starting on http://{host}:{port}")

    # ── Vite dev server ───────────────────────────────────────────────────────
    vite_proc: subprocess.Popen[str] | None = None
    react_dir = Path(__file__).parent.parent / "react"
    if not no_vite and react_dir.exists():
        try:
            vite_proc = _start_vite(settings.vite_port, react_dir)
            typer.echo(
                f"Vite dev server started on http://{settings.vite_host}:{settings.vite_port}"
            )
        except Exception as exc:
            typer.echo(f"Warning: Vite failed to start ({exc})", err=True)

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
            server_thread.join()
        except KeyboardInterrupt:
            pass

    # ── Cleanup ───────────────────────────────────────────────────────────────
    if vite_proc:
        vite_proc.terminate()

    typer.echo("Harness stopped.")


if __name__ == "__main__":
    app()
