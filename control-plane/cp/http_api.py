"""Frontend-facing HTTP shell for the control-plane runtime."""

from __future__ import annotations

import json
import logging
import mimetypes
import sqlite3
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

LOGGER = logging.getLogger("vloop.control_plane.http")


class HttpShellServer:
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
        try:
            server = ThreadingHTTPServer(
                (self.runtime.config.http_host, self.runtime.config.http_port),
                _handler_factory(self.runtime),
            )
            self._server = server
            self._ready.set()
            LOGGER.info(
                "control-plane HTTP shell listening on %s",
                self.runtime.config.shell_url(),
            )
            server.serve_forever(poll_interval=0.25)
        except Exception as exc:  # pragma: no cover - runtime path
            self._startup_error = RuntimeError(
                f"failed to start control-plane HTTP shell: {exc}"
            )
            self._ready.set()


def _handler_factory(runtime: Any):
    dist_dir = runtime.config.repo_root / "src" / "dist"
    index_path = dist_dir / "index.html"

    class ControlPlaneHandler(BaseHTTPRequestHandler):
        server_version = "VLoopControlPlane/0.2"

        def do_GET(self) -> None:  # noqa: N802
            self._dispatch("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._dispatch("POST")

        def do_PUT(self) -> None:  # noqa: N802
            self._dispatch("PUT")

        def do_PATCH(self) -> None:  # noqa: N802
            self._dispatch("PATCH")

        def do_DELETE(self) -> None:  # noqa: N802
            self._dispatch("DELETE")

        def log_message(self, format: str, *args: Any) -> None:
            LOGGER.info("%s - %s", self.client_address[0], format % args)

        def _dispatch(self, method: str) -> None:
            url = urlsplit(self.path)
            path = url.path or "/"
            query = parse_qs(url.query, keep_blank_values=True)

            try:
                if method == "GET" and path == "/health":
                    self._write_json(runtime.health_snapshot())
                    return
                if method == "GET" and path == "/session":
                    self._write_json(runtime.session_snapshot())
                    return
                if method == "GET" and path == "/events/recent":
                    self._write_json(runtime.event_snapshot())
                    return
                if method == "GET" and path == "/window":
                    self._write_json(runtime.window_snapshot())
                    return
                if method == "GET" and path == "/dependencies":
                    self._write_json(runtime.dependency_snapshot())
                    return

                if path.startswith("/api/"):
                    self._handle_api(method, path, query)
                    return

                if method == "GET":
                    self._serve_frontend_asset(path)
                    return

                self._write_error_json(
                    HTTPStatus.METHOD_NOT_ALLOWED,
                    f"method {method} is not supported for {path}",
                )
            except Exception as exc:
                self._handle_exception(exc)

        def _handle_api(
            self, method: str, path: str, query: dict[str, list[str]]
        ) -> None:
            body = (
                self._read_json_body()
                if method in {"POST", "PUT", "PATCH", "DELETE"}
                else {}
            )
            segments = _split_segments(path)

            if (
                segments == ["api", "v1"]
                or segments == ["api", "v1", "bootstrap"]
                or segments == ["api", "v1", "state"]
            ):
                self._require_method(method, {"GET"})
                self._write_json(runtime.bootstrap_payload())
                return

            if segments in (
                ["api", "v1", "catalog", "provider-types"],
                ["api", "v1", "providers", "catalog"],
                ["api", "v1", "provider-catalog"],
                ["api", "v1", "catalog", "providers"],
            ):
                self._require_method(method, {"GET"})
                self._write_json({"providerCatalog": runtime.provider_catalog()})
                return

            if segments == ["api", "v1", "agents", "templates"]:
                self._require_method(method, {"GET"})
                self._write_json({"agentTemplates": runtime.list_agent_templates()})
                return

            if segments == ["api", "v1", "providers"]:
                if method == "GET":
                    self._write_json({"providers": runtime.list_providers()})
                    return
                if method == "POST":
                    provider = runtime.save_provider(body)
                    self._write_json({"provider": provider}, status=HTTPStatus.CREATED)
                    return

            if segments == ["api", "v1", "providers", "test"]:
                self._require_method(method, {"POST"})
                provider_id = _required_string(body, "providerId", "provider_id")
                self._write_json(runtime.test_provider(provider_id))
                return

            if len(segments) == 4 and segments[:3] == ["api", "v1", "providers"]:
                provider_id = unquote(segments[3])
                if method == "GET":
                    provider = runtime.get_provider(provider_id)
                    if provider is None:
                        raise KeyError(f"provider `{provider_id}` was not found")
                    self._write_json({"provider": provider})
                    return
                if method in {"PUT", "PATCH", "POST"}:
                    provider = runtime.save_provider(body, provider_id)
                    self._write_json({"provider": provider})
                    return
                if method == "DELETE":
                    runtime.delete_provider(provider_id)
                    self._write_json({"ok": True, "providerId": provider_id})
                    return

            if len(segments) == 5 and segments[:3] == ["api", "v1", "providers"]:
                provider_id = unquote(segments[3])
                suffix = segments[4]
                if suffix == "test":
                    self._require_method(method, {"POST"})
                    self._write_json(runtime.test_provider(provider_id))
                    return
                if suffix == "secret":
                    self._require_method(method, {"DELETE"})
                    provider = runtime.delete_session_secret(provider_id)
                    self._write_json({"provider": provider})
                    return

            if segments == ["api", "v1", "agents"]:
                if method == "GET":
                    self._write_json({"agents": runtime.list_agents()})
                    return
                if method == "POST":
                    agent = runtime.save_agent(body)
                    self._write_json({"agent": agent}, status=HTTPStatus.CREATED)
                    return

            if segments == ["api", "v1", "agents", "validate"]:
                self._require_method(method, {"POST"})
                self._write_json(runtime.validate_agent(body))
                return

            if len(segments) == 4 and segments[:3] == ["api", "v1", "agents"]:
                agent_id = unquote(segments[3])
                if method == "GET":
                    agent = runtime.get_agent(agent_id)
                    if agent is None:
                        raise KeyError(f"agent `{agent_id}` was not found")
                    self._write_json({"agent": agent})
                    return
                if method in {"PUT", "PATCH", "POST"}:
                    agent = runtime.save_agent(body, agent_id)
                    self._write_json({"agent": agent})
                    return
                if method == "DELETE":
                    runtime.delete_agent(agent_id)
                    self._write_json({"ok": True, "agentId": agent_id})
                    return

            if len(segments) == 5 and segments[:3] == ["api", "v1", "agents"]:
                agent_id = unquote(segments[3])
                suffix = segments[4]
                if suffix == "validate":
                    self._require_method(method, {"POST"})
                    self._write_json(runtime.validate_agent(body, agent_id))
                    return
                if suffix == "invoke":
                    self._require_method(method, {"POST"})
                    invocation = runtime.invoke_agent(agent_id, body)
                    self._write_json(
                        {"invocation": invocation}, status=HTTPStatus.ACCEPTED
                    )
                    return
                if suffix == "invocations":
                    if method == "GET":
                        self._write_json(
                            {"invocations": runtime.list_invocations(agent_id)}
                        )
                        return
                    if method == "POST":
                        invocation = runtime.invoke_agent(agent_id, body)
                        self._write_json(
                            {"invocation": invocation}, status=HTTPStatus.ACCEPTED
                        )
                        return

            if segments == ["api", "v1", "invocations"]:
                if method == "GET":
                    agent_id = _optional_query_value(query, "agentId", "agent_id")
                    self._write_json(
                        {"invocations": runtime.list_invocations(agent_id)}
                    )
                    return
                if method == "POST":
                    agent_id = _required_string(body, "agentId", "agent_id")
                    invocation = runtime.invoke_agent(agent_id, body)
                    self._write_json(
                        {"invocation": invocation}, status=HTTPStatus.ACCEPTED
                    )
                    return

            if len(segments) == 4 and segments[:3] == ["api", "v1", "invocations"]:
                self._require_method(method, {"GET"})
                invocation_id = unquote(segments[3])
                invocation = runtime.get_invocation(invocation_id)
                if invocation is None:
                    raise KeyError(f"invocation `{invocation_id}` was not found")
                self._write_json({"invocation": invocation})
                return

            if len(segments) == 5 and segments[:3] == ["api", "v1", "invocations"]:
                self._require_method(method, {"GET"})
                invocation_id = unquote(segments[3])
                suffix = segments[4]
                if suffix == "events":
                    self._write_json(
                        {
                            "events": runtime.get_invocation_events(invocation_id),
                            "invocationId": invocation_id,
                        }
                    )
                    return

            if segments == ["api", "v1", "invocation-events"]:
                self._require_method(method, {"GET"})
                invocation_id = _optional_query_value(
                    query, "invocationId", "invocation_id"
                )
                if not invocation_id:
                    raise ValueError("query parameter `invocationId` is required")
                self._write_json(
                    {
                        "events": runtime.get_invocation_events(invocation_id),
                        "invocationId": invocation_id,
                    }
                )
                return

            if segments == ["api", "v1", "workloads"]:
                if method == "GET":
                    self._write_json(runtime.list_workloads())
                    return
                if method == "POST":
                    workload = runtime.create_workload(body)
                    self._write_json({"workload": workload}, status=HTTPStatus.CREATED)
                    return

            if len(segments) == 4 and segments[:3] == ["api", "v1", "workloads"]:
                workload_id = unquote(segments[3])
                if method == "GET":
                    self._write_json(runtime.get_workload(workload_id))
                    return
                if method == "DELETE":
                    runtime.remove_workload(workload_id)
                    self._write_json({"ok": True, "workloadId": workload_id})
                    return

            if len(segments) == 5 and segments[:3] == ["api", "v1", "workloads"]:
                workload_id = unquote(segments[3])
                suffix = segments[4]
                if suffix == "start":
                    self._require_method(method, {"POST"})
                    workload = runtime.start_workload(workload_id)
                    self._write_json({"workload": workload})
                    return
                if suffix == "stop":
                    self._require_method(method, {"POST"})
                    workload = runtime.stop_workload(workload_id)
                    self._write_json({"workload": workload})
                    return
                if suffix == "logs":
                    self._require_method(method, {"GET"})
                    self._write_json(runtime.get_workload_logs(workload_id))
                    return

            raise KeyError(f"route `{path}` was not found")

        def _serve_frontend_asset(self, path: str) -> None:
            if index_path.is_file():
                target = _resolve_static_path(dist_dir, path)
                if target is not None and target.is_file():
                    self._write_file(target)
                    return

                if path == "/" or "." not in path.rsplit("/", 1)[-1]:
                    self._write_file(index_path)
                    return

                raise KeyError(f"static asset `{path}` was not found")

            if path == "/":
                self._write_html(_fallback_shell_html(runtime))
                return

            raise KeyError(f"static asset `{path}` was not found")

        def _read_json_body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length <= 0:
                return {}

            raw = self.rfile.read(length)
            if not raw:
                return {}

            try:
                payload = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError("request body must be valid JSON") from exc

            if not isinstance(payload, dict):
                raise ValueError("request body must be a JSON object")
            return payload

        def _require_method(self, method: str, allowed: set[str]) -> None:
            if method not in allowed:
                raise MethodNotAllowedError(method, allowed)

        def _handle_exception(self, exc: Exception) -> None:
            if isinstance(exc, MethodNotAllowedError):
                self._write_error_json(
                    HTTPStatus.METHOD_NOT_ALLOWED,
                    str(exc),
                    extra={"allowed": sorted(exc.allowed)},
                )
                return
            if isinstance(exc, KeyError):
                self._write_error_json(
                    HTTPStatus.NOT_FOUND, _clean_exception_message(exc)
                )
                return
            if isinstance(exc, ValueError):
                self._write_error_json(
                    HTTPStatus.BAD_REQUEST, _clean_exception_message(exc)
                )
                return
            if isinstance(exc, sqlite3.IntegrityError):
                self._write_error_json(
                    HTTPStatus.CONFLICT, _clean_exception_message(exc)
                )
                return
            if isinstance(exc, RuntimeError):
                self._write_error_json(
                    HTTPStatus.CONFLICT, _clean_exception_message(exc)
                )
                return

            LOGGER.exception("control-plane HTTP request failed: %s", exc)
            self._write_error_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "internal control-plane error",
            )

        def _write_json(
            self,
            payload: dict[str, Any] | list[Any] | str | int | float | bool | None,
            *,
            status: HTTPStatus = HTTPStatus.OK,
        ) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _write_error_json(
            self,
            status: HTTPStatus,
            message: str,
            *,
            extra: dict[str, Any] | None = None,
        ) -> None:
            payload: dict[str, Any] = {
                "status": int(status),
                "error": status.phrase,
                "message": message,
            }
            if extra:
                payload.update(extra)
            self._write_json(payload, status=status)

        def _write_html(self, html: str) -> None:
            body = html.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _write_file(self, path: Path) -> None:
            body = path.read_bytes()
            content_type, encoding = mimetypes.guess_type(path.name)
            self.send_response(HTTPStatus.OK)
            self.send_header(
                "Content-Type",
                content_type or "application/octet-stream",
            )
            if encoding:
                self.send_header("Content-Encoding", encoding)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return ControlPlaneHandler


class MethodNotAllowedError(RuntimeError):
    def __init__(self, method: str, allowed: set[str]) -> None:
        self.method = method
        self.allowed = allowed
        allowed_text = ", ".join(sorted(allowed))
        super().__init__(
            f"method {method} is not supported; allowed methods: {allowed_text}"
        )


def _split_segments(path: str) -> list[str]:
    return [segment for segment in path.strip("/").split("/") if segment]


def _optional_query_value(query: dict[str, list[str]], *names: str) -> str | None:
    for name in names:
        values = query.get(name)
        if values:
            value = str(values[0]).strip()
            if value:
                return value
    return None


def _required_string(payload: dict[str, Any], *names: str) -> str:
    for name in names:
        value = payload.get(name)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    raise ValueError(f"one of {', '.join(f'`{name}`' for name in names)} is required")


def _clean_exception_message(exc: Exception) -> str:
    message = str(exc)
    if message.startswith("'") and message.endswith("'"):
        return message[1:-1]
    return message


def _resolve_static_path(dist_dir: Path, request_path: str) -> Path | None:
    raw_path = request_path.lstrip("/")
    if not raw_path:
        return dist_dir / "index.html"

    candidate = (dist_dir / raw_path).resolve()
    try:
        candidate.relative_to(dist_dir.resolve())
    except ValueError:
        return None
    return candidate


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
