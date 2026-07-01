"""Unit tests for non-technical error presentation (task 30.8, Req 20.3).

These verify the user-facing error sanitizer and server-side logging helper in
``cp.http_responders``:

* A 5xx response body carries no traceback / Python type name / file-path
  detail — only a generic non-technical message.
* The server log captures the full (secret-redacted) detail, including a
  traceback, so diagnostics are retained server-side.
* A 4xx user-actionable message still passes through cleaned.
"""

from __future__ import annotations

import json
import logging
from http import HTTPStatus
from typing import Any

from core.event_router import REDACTED
from cp.http_responders import (
    GENERIC_SERVER_ERROR_MESSAGE,
    log_internal_error,
    user_facing_error_message,
    write_error_json,
)


class _FakeWFile:
    def __init__(self) -> None:
        self.chunks: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.chunks.append(data)


class FakeHandler:
    """Minimal stand-in for BaseHTTPRequestHandler used by write_json."""

    def __init__(self) -> None:
        self.status: HTTPStatus | None = None
        self.headers_sent: dict[str, str] = {}
        self.wfile = _FakeWFile()

    def send_response(self, status: HTTPStatus) -> None:
        self.status = status

    def send_header(self, key: str, value: str) -> None:
        self.headers_sent[key] = value

    def end_headers(self) -> None:
        pass

    @property
    def raw_body(self) -> str:
        return b"".join(self.wfile.chunks).decode("utf-8")

    @property
    def body(self) -> Any:
        return json.loads(self.raw_body)


def _boom_with_traceback(detail: str) -> Exception:
    """Raise and catch a RuntimeError so it carries a real traceback."""
    try:

        def _inner() -> None:
            raise RuntimeError(detail)

        _inner()
    except RuntimeError as exc:  # pragma: no cover - control flow only
        return exc
    raise AssertionError("expected RuntimeError")  # pragma: no cover


# ---------------------------------------------------------------------------
# (a) 5xx response body carries no internal detail
# ---------------------------------------------------------------------------


def test_server_error_body_has_no_internal_detail():
    handler = FakeHandler()
    leaked = (
        'Traceback (most recent call last):\n'
        '  File "/srv/cp/http_handler.py", line 42, in _dispatch\n'
        "RuntimeError: connection to 10.0.0.1:5432 refused"
    )

    write_error_json(handler, HTTPStatus.INTERNAL_SERVER_ERROR, leaked)

    assert handler.status == HTTPStatus.INTERNAL_SERVER_ERROR
    assert handler.body["message"] == GENERIC_SERVER_ERROR_MESSAGE

    raw = handler.raw_body
    # No traceback / Python type / file-path / line-number detail leaks.
    assert "Traceback" not in raw
    assert "RuntimeError" not in raw
    assert "http_handler.py" not in raw
    assert "line 42" not in raw
    assert "10.0.0.1" not in raw


def test_user_facing_message_collapses_all_5xx_to_generic():
    for status in (
        HTTPStatus.INTERNAL_SERVER_ERROR,
        HTTPStatus.BAD_GATEWAY,
        HTTPStatus.SERVICE_UNAVAILABLE,
    ):
        msg = user_facing_error_message(status, "raw detail with secret-ish info")
        assert msg == GENERIC_SERVER_ERROR_MESSAGE


# ---------------------------------------------------------------------------
# (b) server log captures redacted detail (with traceback)
# ---------------------------------------------------------------------------


def test_server_log_captures_redacted_traceback(caplog):
    secret = "sk-super-secret-token"
    exc = _boom_with_traceback(f"db auth failed using {secret}")

    logger = logging.getLogger("vloop.test.error_presentation")
    with caplog.at_level(logging.ERROR, logger=logger.name):
        redacted = log_internal_error(
            exc,
            logger=logger,
            context="request failed",
            known_secrets=(secret,),
        )

    # The raw secret never reaches the log; it is replaced by the redaction
    # placeholder.
    assert secret not in redacted
    assert REDACTED in redacted
    # Full diagnostic detail (traceback + type) IS retained server-side.
    assert "Traceback (most recent call last)" in redacted
    assert "RuntimeError" in redacted

    logged = caplog.text
    assert secret not in logged
    assert "request failed" in logged
    assert "Traceback (most recent call last)" in logged


# ---------------------------------------------------------------------------
# (c) 4xx user-actionable messages pass through cleaned
# ---------------------------------------------------------------------------


def test_client_error_message_passes_through():
    handler = FakeHandler()
    write_error_json(
        handler,
        HTTPStatus.BAD_REQUEST,
        "cycle detected involving steps: a, b",
    )
    assert handler.status == HTTPStatus.BAD_REQUEST
    assert handler.body["message"] == "cycle detected involving steps: a, b"


def test_client_error_message_reduced_to_first_line():
    msg = user_facing_error_message(
        HTTPStatus.BAD_REQUEST,
        "field `name` is required\nextra noise line",
    )
    assert msg == "field `name` is required"


def test_client_error_with_leaked_traceback_is_scrubbed():
    leaked = (
        'value error\nTraceback (most recent call last):\n'
        '  File "/srv/x.py", line 9, in f'
    )
    msg = user_facing_error_message(HTTPStatus.BAD_REQUEST, leaked)
    assert "Traceback" not in msg
    assert "x.py" not in msg
    assert msg != ""
