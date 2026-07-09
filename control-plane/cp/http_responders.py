"""HTTP responders — JSON, error, HTML, and file response helpers."""

from __future__ import annotations

import json as _json
import logging
import mimetypes
import traceback as _traceback
from http import HTTPStatus
from pathlib import Path
from typing import Any

from core.event_router import redact_secrets

LOGGER = logging.getLogger("vloop.control_plane.http")

# Generic, non-technical message surfaced to users for any server-side (5xx)
# or otherwise unexpected failure. It deliberately carries no internal detail:
# no stack traces, exception types, file paths, or line numbers (Requirement
# 20.3).
GENERIC_SERVER_ERROR_MESSAGE = (
    "An unexpected error occurred. Please try again or contact support."
)

# Fallback message for a client (4xx) error whose detail looks like it leaked
# internal/technical content. Normal client errors carry short, user-actionable
# text that passes through untouched; this only triggers as a defensive scrub.
GENERIC_CLIENT_ERROR_MESSAGE = (
    "The request could not be completed. Please check your input and try again."
)

# Markers that indicate a message has leaked raw internal detail (a traceback,
# a Python type name in a frame, or a source path with a line number).
_INTERNAL_DETAIL_MARKERS = (
    "Traceback (most recent call last)",
    'File "',
    ", line ",
)


def user_facing_error_message(
    status: HTTPStatus | int,
    message: str,
) -> str:
    """Return a non-technical, user-facing error message (Requirement 20.3).

    Server errors (5xx) and any unexpected status collapse to a single generic
    message so raw exception detail — stack traces, Python type names, file
    paths, and line numbers — can never reach the user.

    Client errors (4xx) carry user-actionable detail, so the (already cleaned)
    *message* is surfaced. As defense-in-depth it is reduced to its first line
    and, if it still looks like leaked internal detail, replaced with a generic
    client-error message.
    """
    status_code = int(status)
    if status_code >= 500 or status_code < 400:
        return GENERIC_SERVER_ERROR_MESSAGE

    first_line = str(message).strip().splitlines()[0] if str(message).strip() else ""
    if not first_line:
        return GENERIC_CLIENT_ERROR_MESSAGE
    if any(marker in str(message) for marker in _INTERNAL_DETAIL_MARKERS):
        return GENERIC_CLIENT_ERROR_MESSAGE
    return first_line


def log_internal_error(
    exc: BaseException,
    *,
    logger: logging.Logger | None = None,
    context: str = "",
    known_secrets: tuple[str, ...] = (),
) -> str:
    """Log full exception detail (with traceback) to the server log.

    The user-facing response never includes this detail; it is retained
    server-side for diagnostics (Requirement 20.3). Secret values are redacted
    before logging by reusing :func:`core.event_router.redact_secrets`, so a
    known secret that appears in the exception text or traceback is scrubbed and
    never written to the log.

    Returns the redacted detail string (useful for testing / callers that want
    to forward it to another sink).
    """
    detail = "".join(
        _traceback.format_exception(type(exc), exc, exc.__traceback__)
    )
    redacted = redact_secrets(detail, tuple(s for s in known_secrets if s))
    target = logger or LOGGER
    prefix = f"{context}: " if context else ""
    target.error("%s%s", prefix, redacted)
    return redacted


def _send_security_headers(handler: Any) -> None:
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("X-Frame-Options", "DENY")
    handler.send_header("X-XSS-Protection", "1; mode=block")
    handler.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    handler.send_header(
        "Content-Security-Policy",
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "connect-src 'self' ws: wss:; "
        "img-src 'self' data:; "
        "font-src 'self' data:;"
    )

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
    _send_security_headers(handler)
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
        "message": user_facing_error_message(status, message),
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
    _send_security_headers(handler)
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
    _send_security_headers(handler)
    handler.end_headers()
    handler.wfile.write(body)
