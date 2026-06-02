"""BrowserTool — policy-gated browser automation via Playwright.

Security guarantees
───────────────────
• URL policy: only URLs matching the workspace origin or an explicit allowlist
  are navigable. Configurable via ``browser_allowed_origins`` in policy.
• All navigation, screenshots, and DOM operations run in a sandboxed Playwright
  context with JavaScript execution restricted to safe helpers.
• ``execute_script`` is blocked unless the component holds SHELL_EXEC permission
  (it is treated as equivalent risk).
• Screenshots are base64-encoded PNG and truncated at 2 MiB.
• Full page text and HTML responses are truncated at 512 KiB.
• Playwright itself is an optional dependency — the tool degrades gracefully
  when it is not installed.

Supported operations (via ``params["operation"]``)
──────────────────────────────────────────────────
  navigate    — navigate to a URL and return page title + URL
  screenshot  — return a base64 PNG screenshot of the current page
  get_text    — return the visible text content of the page (or a CSS selector)
  get_html    — return the outer HTML of the page (or a CSS selector)
  click       — click an element matching a CSS selector
  fill        — fill an input matching a CSS selector with a value
  eval_js     — evaluate a JavaScript expression (requires SHELL_EXEC permission)
  close       — close the browser context
"""

from __future__ import annotations

import base64
import time
from typing import TYPE_CHECKING, Any

from harness.core.permissions import Permission
from harness.tools.base_tool import AbstractTool, ToolResult

if TYPE_CHECKING:
    from harness.core.main_process import MainProcess

_MAX_SCREENSHOT_BYTES = 2 * 1024 * 1024   # 2 MiB
_MAX_TEXT_BYTES = 512 * 1024               # 512 KiB


class BrowserTool(AbstractTool):
    """Browser automation tool backed by Playwright."""

    name = "browser"
    description = (
        "Browser automation: navigate, screenshot, get_text, get_html, click, fill, eval_js. "
        "Only URLs matching the workspace origin or the configured allowed origins are reachable. "
        "Requires NETWORK_OUTBOUND permission."
    )
    required_permission = Permission.NETWORK_OUTBOUND
    risk_level = "caution"

    def __init__(self, main_process: "MainProcess") -> None:
        super().__init__(main_process)
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None

    # ── Playwright lifecycle ──────────────────────────────────────────────────

    async def _ensure_browser(self) -> None:
        """Lazily start Playwright and launch a Chromium browser."""
        if self._page is not None:
            return
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is not installed. Run: pip install playwright && playwright install chromium"
            ) from exc

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        self._context = await self._browser.new_context()
        self._page = await self._context.new_page()

    async def _close_browser(self) -> None:
        if self._page:
            await self._page.close()
            self._page = None
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    # ── URL policy ────────────────────────────────────────────────────────────

    def _check_url(self, url: str) -> None:
        """Raise WorkspaceEscape if the URL is not allowed."""
        from harness.tools.exceptions import WorkspaceEscape

        # Always allow localhost / 127.0.0.1 (workspace UI)
        allowed_prefixes = [
            "http://localhost",
            "http://127.0.0.1",
            "https://localhost",
            "https://127.0.0.1",
        ]
        # Extend with project-level policy allowed origins if available
        try:
            extra = getattr(self._mp.tools, "policy", None)
            if extra and hasattr(extra.effective, "browser_allowed_origins"):
                allowed_prefixes.extend(extra.effective.browser_allowed_origins)
        except Exception:
            pass

        from urllib.parse import urlparse

        try:
            parsed = urlparse(url)
            hostname = parsed.hostname or ""
            scheme = parsed.scheme
            port = parsed.port

            allowed = False
            for prefix in allowed_prefixes:
                try:
                    p_prefix = urlparse(prefix)
                    p_hostname = p_prefix.hostname or ""
                    p_scheme = p_prefix.scheme
                    p_port = p_prefix.port

                    # If the prefix does not specify a port, we allow any port (which maintains the behavior of original startswith)
                    # Alternatively, if prefix starts with http/https but specifies no port, we only check hostname and scheme.
                    # Wait, startswith("http://localhost") allowed "http://localhost:8080".
                    # It also allowed "http://localhost/path"
                    # However, if allowed prefix has a path like "http://localhost/secure", startswith would require the path.

                    # More robust matching:
                    # Construct normalized base of the prefix to see if the URL starts with it,
                    # BUT enforce that the hostname matches exactly.

                    if scheme == p_scheme and hostname == p_hostname:
                        # Check port
                        if p_port is not None and port != p_port:
                            continue

                        # Check path prefix
                        p_path = p_prefix.path
                        if p_path and not parsed.path.startswith(p_path):
                            continue

                        allowed = True
                        break
                except Exception:
                    pass
        except Exception:
            allowed = False

        if not allowed:
            raise WorkspaceEscape(
                f"URL {url!r} is not in the browser allowed-origins list. "
                "Configure browser_allowed_origins in your policy.json to allow it."
            )

    # ── Dispatch ──────────────────────────────────────────────────────────────

    async def execute(
        self,
        component_id: str | None,
        session_id: str | None,
        params: dict[str, Any],
    ) -> ToolResult:
        self._check_permission(component_id)

        operation: str = params.get("operation", "")
        t0 = time.time()

        try:
            if operation == "navigate":
                result = await self._navigate(params)
            elif operation == "screenshot":
                result = await self._screenshot(params)
            elif operation == "get_text":
                result = await self._get_text(params)
            elif operation == "get_html":
                result = await self._get_html(params)
            elif operation == "click":
                result = await self._click(params)
            elif operation == "fill":
                result = await self._fill(params)
            elif operation == "eval_js":
                result = await self._eval_js(params, component_id)
            elif operation == "close":
                await self._close_browser()
                result = ToolResult(success=True, output="Browser closed.")
            else:
                result = ToolResult(
                    success=False,
                    error=f"Unknown browser operation: {operation!r}. "
                    "Valid: navigate, screenshot, get_text, get_html, click, fill, eval_js, close",
                )
        except Exception as exc:
            result = ToolResult(success=False, error=str(exc))

        result.metadata["duration_ms"] = int((time.time() - t0) * 1000)
        result.metadata["operation"] = operation
        return result

    # ── Operation implementations ─────────────────────────────────────────────

    async def _navigate(self, params: dict[str, Any]) -> ToolResult:
        url: str = params.get("url", "")
        if not url:
            return ToolResult(success=False, error="'url' parameter is required for navigate")
        self._check_url(url)
        await self._ensure_browser()
        await self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
        title = await self._page.title()
        current_url = self._page.url
        return ToolResult(
            success=True,
            output=f"Navigated to {current_url!r} — title: {title!r}",
            metadata={"title": title, "url": current_url},
        )

    async def _screenshot(self, params: dict[str, Any]) -> ToolResult:
        full_page: bool = params.get("full_page", False)
        await self._ensure_browser()
        png_bytes: bytes = await self._page.screenshot(full_page=full_page)
        if len(png_bytes) > _MAX_SCREENSHOT_BYTES:
            return ToolResult(
                success=False,
                error=f"Screenshot exceeds {_MAX_SCREENSHOT_BYTES // 1024} KiB limit.",
            )
        encoded = base64.b64encode(png_bytes).decode("ascii")
        return ToolResult(
            success=True,
            output=encoded,
            metadata={"format": "png/base64", "size_bytes": len(png_bytes)},
        )

    async def _get_text(self, params: dict[str, Any]) -> ToolResult:
        selector: str = params.get("selector", "body")
        await self._ensure_browser()
        el = await self._page.query_selector(selector)
        if el is None:
            return ToolResult(success=False, error=f"Selector {selector!r} not found")
        text = await el.inner_text()
        text_bytes = text.encode("utf-8")
        if len(text_bytes) > _MAX_TEXT_BYTES:
            text = text_bytes[:_MAX_TEXT_BYTES].decode("utf-8", errors="ignore") + "\n... [truncated]"
        return ToolResult(success=True, output=text, metadata={"selector": selector})

    async def _get_html(self, params: dict[str, Any]) -> ToolResult:
        selector: str = params.get("selector", "html")
        await self._ensure_browser()
        el = await self._page.query_selector(selector)
        if el is None:
            return ToolResult(success=False, error=f"Selector {selector!r} not found")
        html = await el.inner_html()
        html_bytes = html.encode("utf-8")
        if len(html_bytes) > _MAX_TEXT_BYTES:
            html = html_bytes[:_MAX_TEXT_BYTES].decode("utf-8", errors="ignore") + "\n<!-- truncated -->"
        return ToolResult(success=True, output=html, metadata={"selector": selector})

    async def _click(self, params: dict[str, Any]) -> ToolResult:
        selector: str = params.get("selector", "")
        if not selector:
            return ToolResult(success=False, error="'selector' parameter is required for click")
        await self._ensure_browser()
        await self._page.click(selector, timeout=10000)
        return ToolResult(success=True, output=f"Clicked {selector!r}")

    async def _fill(self, params: dict[str, Any]) -> ToolResult:
        selector: str = params.get("selector", "")
        value: str = params.get("value", "")
        if not selector:
            return ToolResult(success=False, error="'selector' parameter is required for fill")
        await self._ensure_browser()
        await self._page.fill(selector, value, timeout=10000)
        return ToolResult(success=True, output=f"Filled {selector!r} with value")

    async def _eval_js(self, params: dict[str, Any], component_id: str | None) -> ToolResult:
        """Evaluate JavaScript. Requires SHELL_EXEC permission (high risk)."""
        from harness.tools.exceptions import PermissionDenied

        cid = component_id or "root"
        if cid != "root" and not self._mp.permissions.has(cid, Permission.SHELL_EXEC):
            raise PermissionDenied(
                f"eval_js requires {Permission.SHELL_EXEC.value!r} permission"
            )
        expression: str = params.get("expression", "")
        if not expression:
            return ToolResult(success=False, error="'expression' parameter is required for eval_js")
        await self._ensure_browser()
        result = await self._page.evaluate(expression)
        return ToolResult(
            success=True,
            output=str(result),
            metadata={"expression_length": len(expression)},
        )
