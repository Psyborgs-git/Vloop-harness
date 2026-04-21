"""PyWebView root window — wraps the React Root UI in a native window."""

from __future__ import annotations

import threading
from typing import Any

try:
    import webview  # type: ignore[import-untyped]

    _WEBVIEW_AVAILABLE = True
except ImportError:
    _WEBVIEW_AVAILABLE = False


class RootWindow:
    """
    Opens a single native window pointing at the harness Root UI.

    Falls back to a simple browser-open when pywebview is not installed
    so that headless / dev environments still work.
    """

    def __init__(self, url: str, title: str = "Vloop Harness", width: int = 1280, height: int = 800) -> None:
        self.url = url
        self.title = title
        self.width = width
        self.height = height
        self._window: Any | None = None

    def open(self) -> None:
        if not _WEBVIEW_AVAILABLE:
            import webbrowser

            webbrowser.open(self.url)
            return

        self._window = webview.create_window(
            title=self.title,
            url=self.url,
            width=self.width,
            height=self.height,
            resizable=True,
        )
        webview.start(debug=False)

    def focus(self) -> None:
        """Bring the window to the front.  Called from the global hotkey thread."""
        if self._window is not None:
            try:
                self._window.show()
            except Exception:
                pass
            # macOS: activate the app so the window comes to front
            try:
                from AppKit import NSApplication  # type: ignore[import-untyped]
                NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            except ImportError:
                pass
        else:
            import webbrowser
            webbrowser.open(self.url)

    def open_nonblocking(self) -> threading.Thread:
        t = threading.Thread(target=self.open, daemon=True)
        t.start()
        return t
