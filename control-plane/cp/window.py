"""Python-owned window manager backed by pywebview."""

from __future__ import annotations

import importlib
import logging
import threading
import time
from contextlib import suppress
from dataclasses import asdict, dataclass
from typing import Any, Callable

from cp.config_service import ControlPlaneConfig

LOGGER = logging.getLogger("vloop.control_plane.window")

_BOOTSTRAP_HTML = """<!doctype html>
<html lang='en'>
  <head>
    <meta charset='UTF-8' />
    <meta name='viewport' content='width=device-width, initial-scale=1.0' />
    <title>VLoop</title>
    <style>
      :root { color-scheme: dark; }
      body {
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        background: radial-gradient(circle at top, #1f2937, #0f172a 60%);
        color: #e5e7eb;
        font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }
      .card {
        width: min(36rem, calc(100vw - 3rem));
        border-radius: 20px;
        padding: 2rem;
        background: rgba(15, 23, 42, 0.82);
        border: 1px solid rgba(148, 163, 184, 0.18);
        box-shadow: 0 24px 80px rgba(15, 23, 42, 0.45);
      }
      h1 { margin: 0 0 0.75rem; font-size: 1.8rem; }
      p { margin: 0; color: #cbd5e1; line-height: 1.5; }
    </style>
  </head>
  <body>
    <section class='card'>
      <h1>VLoop is starting</h1>
      <p>The Python Control Plane is preparing the local HTTP shell and registering with the kernel.</p>
    </section>
  </body>
</html>
"""


@dataclass(slots=True)
class WindowSnapshot:
    backend: str
    is_open: bool
    open_requests: int
    last_open_reason: str | None
    last_opened_at_unix_ms: int | None
    last_focused_at_unix_ms: int | None
    shell_url: str | None
    loaded_url: str | None
    last_loaded_at_unix_ms: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WindowManager:
    def __init__(self, config: ControlPlaneConfig) -> None:
        self._config = config
        self._lock = threading.RLock()
        self._allow_destroy = False
        self._webview: Any | None = None
        self._window: Any | None = None
        self._on_quit_requested: Callable[[], None] | None = None
        self._snapshot = WindowSnapshot(
            backend="pywebview",
            is_open=not config.window_hidden_until_open,
            open_requests=0,
            last_open_reason=None,
            last_opened_at_unix_ms=None,
            last_focused_at_unix_ms=None,
            shell_url=None,
            loaded_url=None,
            last_loaded_at_unix_ms=None,
        )

    def start(self, on_gui_ready: Callable[[], None]) -> None:
        webview_module = _load_webview_module()
        window = webview_module.create_window(
            self._config.window_title,
            html=_BOOTSTRAP_HTML,
            width=self._config.window_width,
            height=self._config.window_height,
            min_size=(960, 640),
            hidden=False,
            resizable=True,
            focus=True,
            text_select=True,
            confirm_close=False,
        )
        window.events.closing += self._on_closing
        window.events.closed += self._on_closed
        window.events.loaded += self._on_loaded
        window.events.shown += self._on_shown

        self._webview = webview_module
        self._window = window

        webview_module.start(
            func=self._start_runtime_callback,
            args=(on_gui_ready,),
            debug=self._config.window_debug,
            http_server=False,
            private_mode=True,
        )

    def attach_shell_url(self, shell_url: str) -> None:
        with self._lock:
            self._snapshot.shell_url = shell_url
            window = self._window
            loaded_url = self._snapshot.loaded_url

        if window is None:
            return

        if loaded_url == shell_url:
            return

        LOGGER.info("loading control-plane shell at %s", shell_url)
        try:
            window.load_url(shell_url)
        except Exception:  # pragma: no cover - GUI runtime path
            LOGGER.exception("failed to load control-plane shell URL %s", shell_url)

    def open_main_window(self, reason: str = "manual request") -> WindowSnapshot:
        with self._lock:
            now = _now_unix_ms()
            snapshot = self._snapshot
            snapshot.open_requests += 1
            snapshot.last_open_reason = reason
            if snapshot.last_opened_at_unix_ms is None:
                snapshot.last_opened_at_unix_ms = now
            snapshot.last_focused_at_unix_ms = now
            snapshot.is_open = True
            shell_url = snapshot.shell_url
            loaded_url = snapshot.loaded_url
            window = self._window
            current = WindowSnapshot(**asdict(snapshot))

        if window is not None:
            try:
                if shell_url and loaded_url != shell_url:
                    window.load_url(shell_url)
                window.show()
                with suppress(Exception):
                    window.restore()
                with suppress(Exception):
                    window.evaluate_js("window.focus();")
            except Exception:  # pragma: no cover - GUI runtime path
                LOGGER.exception("failed to show/focus the VLoop window")

        LOGGER.info(
            "window manager (%s): show/focus main window because %s",
            current.backend,
            reason,
        )
        return current

    def set_quit_callback(self, callback: Callable[[], None]) -> None:
        """Register a callback invoked when the user requests quit (title-bar X or equivalent)."""
        with self._lock:
            self._on_quit_requested = callback

    def shutdown(self, reason: str = "shutdown requested") -> None:
        with self._lock:
            self._allow_destroy = True
            self._snapshot.is_open = False
            window = self._window

        LOGGER.info("destroying pywebview window because %s", reason)
        if window is not None:
            with suppress(Exception):
                window.destroy()

    def snapshot(self) -> WindowSnapshot:
        with self._lock:
            return WindowSnapshot(**asdict(self._snapshot))

    def _start_runtime_callback(self, callback: Callable[[], None]) -> None:
        callback()

    def _on_closing(self, window: Any) -> bool | None:
        with self._lock:
            if self._allow_destroy:
                self._snapshot.is_open = False
                return None  # let pywebview close the window

            self._snapshot.is_open = False
            on_quit = self._on_quit_requested

        if on_quit is not None:
            LOGGER.info(
                "user requested quit via title-bar — dispatching shutdown cascade"
            )
            # Allow destroy so the quit cascade can close the window cleanly.
            # The quit callback is responsible for stopping HTTP + signalling shutdown.
            with self._lock:
                self._allow_destroy = True
            # Let pywebview close the window; the quit callback handles the rest.
            # We invoke it after returning True so pywebview's close completes.
            # Use a 0-delay timer so the event loop processes the close first.
            import threading

            threading.Thread(target=on_quit, daemon=True).start()
            return None  # allow pywebview to destroy the window
        else:
            LOGGER.info(
                "hiding VLoop main window instead of closing the control-plane process"
            )
            with suppress(Exception):
                window.hide()
        return False

    def _on_closed(self, _window: Any) -> None:
        with self._lock:
            self._snapshot.is_open = False
        LOGGER.info("pywebview window closed")

    def _on_loaded(self, window: Any) -> None:
        loaded_url: str | None = None
        with suppress(Exception):
            loaded_url = window.get_current_url()

        with self._lock:
            self._snapshot.loaded_url = loaded_url
            self._snapshot.last_loaded_at_unix_ms = _now_unix_ms()

        LOGGER.info("pywebview loaded URL %s", loaded_url)

    def _on_shown(self, window: Any) -> None:
        should_hide = False
        with self._lock:
            if (
                self._config.window_hidden_until_open
                and self._snapshot.open_requests == 0
            ):
                self._snapshot.is_open = False
                should_hide = True
            else:
                self._snapshot.is_open = True
                if self._snapshot.last_opened_at_unix_ms is None:
                    self._snapshot.last_opened_at_unix_ms = _now_unix_ms()

        if should_hide:
            with suppress(Exception):
                window.hide()


def _load_webview_module() -> Any:
    try:
        return importlib.import_module("webview")
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on local env
        raise RuntimeError(
            "pywebview is required to open the VLoop desktop window. "
            "Install control-plane dependencies first."
        ) from exc


def _now_unix_ms() -> int:
    return int(time.time() * 1000)
