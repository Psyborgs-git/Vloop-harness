"""ControlPlaneApplication and bootstrap entry point."""

from __future__ import annotations

import asyncio
import logging
import signal
import threading
from contextlib import suppress
from typing import Any

from cp.config_service import ControlPlaneConfig, load_active_config
from cp.runtime import ControlPlaneRuntime
from cp.window import WindowManager

LOGGER = logging.getLogger("vloop.control_plane")


class ControlPlaneApplication:
    """Top-level application that wires the runtime, window, and signal handlers."""

    def __init__(self, config: ControlPlaneConfig) -> None:
        self.config = config
        self.window_manager = WindowManager(config)
        self.runtime = ControlPlaneRuntime(config, self.window_manager)
        self._runtime_thread: threading.Thread | None = None

    def run(self) -> None:
        self._install_signal_handlers()
        self.window_manager.start(self._start_runtime_thread)

    def _start_runtime_thread(self) -> None:
        if self._runtime_thread and self._runtime_thread.is_alive():
            return

        self._runtime_thread = threading.Thread(
            target=self._run_runtime_thread,
            name="vloop-control-plane-runtime",
            daemon=True,
        )
        self._runtime_thread.start()

    def _run_runtime_thread(self) -> None:
        try:
            asyncio.run(self.runtime.run())
        except Exception:
            LOGGER.exception("control-plane runtime crashed")
            raise
        finally:
            self.window_manager.shutdown("control-plane runtime exited")

    def _install_signal_handlers(self) -> None:
        def handle_signal(signum: int, _frame: Any) -> None:
            LOGGER.info("received process signal %s", signum)
            self.runtime.request_shutdown()
            self.window_manager.shutdown(f"received signal {signum}")

        for sig in (signal.SIGINT, signal.SIGTERM):
            with suppress(ValueError):
                signal.signal(sig, handle_signal)


def bootstrap() -> None:
    """Entry point: load config, create the application, and run."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    config = load_active_config()
    LOGGER.info(
        "bootstrapping Python control plane against %s with shell %s",
        config.kernel_endpoint,
        config.shell_url(),
    )
    ControlPlaneApplication(config).run()
