"""HTTP utilities — path parsing, query helpers, validation, and fallback HTML."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from cp.http_responders import write_file, write_html


def split_segments(path: str) -> list[str]:
    """Split a URL path into non-empty segments."""
    return [segment for segment in path.strip("/").split("/") if segment]


def optional_query_value(query: dict[str, list[str]], *names: str) -> str | None:
    """Extract the first non-empty value from query parameters."""
    for name in names:
        values = query.get(name)
        if values:
            value = str(values[0]).strip()
            if value:
                return value
    return None


def required_string(payload: dict[str, Any], *names: str) -> str:
    """Extract a required string field from a payload, trying multiple names."""
    for name in names:
        value = payload.get(name)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    raise ValueError(f"one of {', '.join(f'`{name}`' for name in names)} is required")


def clean_exception_message(exc: Exception) -> str:
    """Strip wrapping quotes from exception messages."""
    message = str(exc)
    if message.startswith("'") and message.endswith("'"):
        return message[1:-1]
    return message


def resolve_static_path(dist_dir: Path, request_path: str) -> Path | None:
    """Safely resolve a static asset path within the dist directory."""
    raw_path = request_path.lstrip("/")
    if not raw_path:
        return dist_dir / "index.html"

    candidate = (dist_dir / raw_path).resolve()
    try:
        candidate.relative_to(dist_dir.resolve())
    except ValueError:
        return None
    return candidate


def serve_frontend_asset(handler: Any, runtime: Any, path: str) -> None:
    """Serve a built frontend asset or fall back to the bootstrap HTML."""
    dist_dir = runtime.config.repo_root / "src" / "dist"
    index_path = dist_dir / "index.html"

    if index_path.is_file():
        target = resolve_static_path(dist_dir, path)
        if target is not None and target.is_file():
            write_file(handler, target)
            return

        if path == "/" or "." not in path.rsplit("/", 1)[-1]:
            write_file(handler, index_path)
            return

        raise KeyError(f"static asset `{path}` was not found")

    if path == "/":
        write_html(handler, _fallback_shell_html(runtime))
        return

    raise KeyError(f"static asset `{path}` was not found")


def read_json_body(handler: Any) -> dict[str, Any]:
    """Read and parse a JSON request body."""
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length <= 0:
        return {}

    raw = handler.rfile.read(length)
    if not raw:
        return {}

    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("request body must be valid JSON") from exc

    if not isinstance(payload, dict):
        raise ValueError("request body must be a JSON object")
    return payload


def require_method(method: str, allowed: set[str]) -> None:
    """Raise MethodNotAllowedError if *method* is not in *allowed*."""
    if method not in allowed:
        from cp.http_api import MethodNotAllowedError

        raise MethodNotAllowedError(method, allowed)


def _fallback_shell_html(runtime: Any) -> str:
    title = runtime.config.window_title
    dist_hint = runtime.config.repo_root / "src" / "dist"
    return f"""<!doctype html>
<html lang='en'>
  <head>
    <meta charset='UTF-8' />
    <meta name='viewport' content='width=device-width, initial-scale=1.0' />
    <title>{title}</title>
    <style>
      :root {{ color-scheme: dark; }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        background: #0f172a;
        color: #e2e8f0;
        font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      }}
      .card {{
        width: min(42rem, calc(100vw - 3rem));
        padding: 1.5rem;
        border-radius: 18px;
        background: rgba(15, 23, 42, 0.92);
        border: 1px solid rgba(148, 163, 184, 0.18);
      }}
      h1 {{ margin: 0 0 0.75rem; font-size: 1.65rem; }}
      p {{ margin: 0.4rem 0; line-height: 1.55; color: #cbd5e1; }}
      code {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
    </style>
  </head>
  <body>
    <section class='card'>
      <h1>{title}</h1>
      <p>The Control Plane HTTP server is running, but the built React bundle was not found.</p>
      <p>Expected frontend bundle location: <code>{dist_hint}</code></p>
      <p>Build the UI from <code>src/</code> with <code>npm run build</code>, then reopen the window.</p>
    </section>
  </body>
</html>
"""
