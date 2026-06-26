"""HTTP shell server — lightweight ThreadingHTTPServer wrapper."""

from __future__ import annotations

import logging
import threading
from http.server import ThreadingHTTPServer
from typing import Any

LOGGER = logging.getLogger("vloop.control_plane.http")


class HttpShellServer:
    """Starts/stops a threaded HTTP server that serves the frontend and API."""

    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._startup_error: RuntimeError | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._thread = threading.Thread(
            target=self._serve,
            name="vloop-control-plane-http",
            daemon=True,
        )
        self._thread.start()

        if not self._ready.wait(timeout=10):
            raise RuntimeError("timed out while starting the control-plane HTTP shell")
        if self._startup_error is not None:
            raise self._startup_error

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=5)

    def _serve(self) -> None:
        from cp.http_handler import handler_factory

        try:
            server = ThreadingHTTPServer(
                (self.runtime.config.http_host, self.runtime.config.http_port),
                handler_factory(self.runtime),
            )
            self._server = server
            self._ready.set()
            LOGGER.info(
                "control-plane HTTP shell listening on %s",
                self.runtime.config.shell_url(),
            )
            server.serve_forever(poll_interval=0.25)
        except Exception as exc:
            self._startup_error = RuntimeError(
                f"failed to start control-plane HTTP shell: {exc}"
            )
            self._ready.set()
