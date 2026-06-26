"""HTTP responders — JSON, error, HTML, and file response helpers."""

from __future__ import annotations

import json as _json
import mimetypes
from http import HTTPStatus
from pathlib import Path
from typing import Any


def write_json(
    handler: Any,
    payload: dict[str, Any] | list[Any] | str | int | float | bool | None,
    *,
    status: HTTPStatus = HTTPStatus.OK,
) -> None:
    body = _json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def write_error_json(
    handler: Any,
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
    write_json(handler, payload, status=status)


def write_html(handler: Any, html: str) -> None:
    body = html.encode("utf-8")
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def write_file(handler: Any, path: Path) -> None:
    body = path.read_bytes()
    content_type, encoding = mimetypes.guess_type(path.name)
    handler.send_response(HTTPStatus.OK)
    handler.send_header(
        "Content-Type",
        content_type or "application/octet-stream",
    )
    if encoding:
        handler.send_header("Content-Encoding", encoding)
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
