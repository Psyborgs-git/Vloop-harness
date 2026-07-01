# Feature: orchestration-engine-completion, Property 44: User-facing errors carry no raw stack traces
"""Property-based test for user-facing error message sanitization.

Validates: Requirements 20.3

Property 44 — User-facing errors carry no raw stack traces:
For an arbitrary exception/message (including ones embedding fabricated
tracebacks, source file paths, Python type names, and secret-like tokens), the
user-facing error JSON body produced via ``write_error_json`` (and the helper
``user_facing_error_message``) never exposes raw internal detail. For any 5xx
response the surfaced message is exactly the generic server message; for any
4xx response the defensive scrub guarantees no traceback/file-path markers
leak. This validates the actual serialized HTTP response body, not just the
helper return value.
"""

from __future__ import annotations

import json
from http import HTTPStatus
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from cp.http_responders import (
    GENERIC_CLIENT_ERROR_MESSAGE,
    GENERIC_SERVER_ERROR_MESSAGE,
    user_facing_error_message,
    write_error_json,
)

# Internal-detail markers that must NEVER appear in a user-facing message body.
_FORBIDDEN_MARKERS = (
    "Traceback (most recent call last)",
    'File "',
    ", line ",
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


# A representative mix of 4xx (user-actionable) and 5xx (server) statuses.
_CLIENT_STATUSES = [
    HTTPStatus.BAD_REQUEST,
    HTTPStatus.UNAUTHORIZED,
    HTTPStatus.FORBIDDEN,
    HTTPStatus.NOT_FOUND,
    HTTPStatus.CONFLICT,
    HTTPStatus.UNPROCESSABLE_ENTITY,
    HTTPStatus.TOO_MANY_REQUESTS,
]
_SERVER_STATUSES = [
    HTTPStatus.INTERNAL_SERVER_ERROR,
    HTTPStatus.NOT_IMPLEMENTED,
    HTTPStatus.BAD_GATEWAY,
    HTTPStatus.SERVICE_UNAVAILABLE,
    HTTPStatus.GATEWAY_TIMEOUT,
]

_http_status = st.sampled_from(_CLIENT_STATUSES + _SERVER_STATUSES)

# Fragments that look like leaked internal/technical detail.
_leaky_fragments = st.sampled_from(
    [
        "Traceback (most recent call last):",
        '  File "/srv/cp/http_handler.py", line 42, in _dispatch',
        '  File "C:\\app\\core\\engine.py", line 7, in run',
        "RuntimeError: something exploded",
        "ValueError: bad value at 0xdeadbeef",
        "KeyError: 'missing'",
        "ConnectionRefusedError: [Errno 111] Connection refused",
        "sk-super-secret-token-abc123",
        "password=hunter2; api_key=AKIA1234567890",
        "  at module.function (file.py:99)",
        "/usr/lib/python3.11/site-packages/foo/bar.py",
    ]
)

# Arbitrary free text — may contain newlines, control chars, unicode.
_free_text = st.text(
    alphabet=st.characters(min_codepoint=1, max_codepoint=0x2FFF),
    max_size=200,
)


def _exception_message() -> st.SearchStrategy[str]:
    """Build diverse, possibly-leaky multi-line exception messages."""
    line = st.one_of(_leaky_fragments, _free_text)
    return st.lists(line, min_size=0, max_size=6).map("\n".join)


@settings(max_examples=200, deadline=None)
@given(status=_http_status, message=_exception_message())
def test_user_facing_error_never_leaks_internal_detail(
    status: HTTPStatus, message: str
) -> None:
    """The serialized error body never exposes raw stack-trace markers.

    Validates: Requirements 20.3
    """
    handler = FakeHandler()
    write_error_json(handler, status, message)

    # Status is echoed faithfully; body is valid JSON with a message field.
    assert handler.status == status
    body = handler.body
    surfaced = body["message"]
    assert isinstance(surfaced, str)

    # The helper and the serialized body must agree.
    assert surfaced == user_facing_error_message(status, message)

    # No internal-detail markers leak in the full serialized response body,
    # regardless of status class.
    raw = handler.raw_body
    for marker in _FORBIDDEN_MARKERS:
        assert marker not in raw, f"leaked marker {marker!r} for status {status}"
        assert marker not in surfaced

    if int(status) >= 500:
        # 5xx collapses to exactly the generic server message.
        assert surfaced == GENERIC_SERVER_ERROR_MESSAGE
    else:
        # 4xx is user-actionable: either cleaned first-line passthrough or the
        # generic client fallback, but never empty and never leaking markers.
        assert surfaced != ""
        # A single-line surfaced message (no embedded newlines).
        assert "\n" not in surfaced
        # If the original looked like leaked internal detail, it must have been
        # replaced by the generic client message.
        if any(m in message for m in _FORBIDDEN_MARKERS):
            assert surfaced == GENERIC_CLIENT_ERROR_MESSAGE


@settings(max_examples=200, deadline=None)
@given(status=st.sampled_from(_SERVER_STATUSES), message=_exception_message())
def test_all_server_errors_collapse_to_generic(
    status: HTTPStatus, message: str
) -> None:
    """Every 5xx message is exactly the generic server message.

    Validates: Requirements 20.3
    """
    assert user_facing_error_message(status, message) == GENERIC_SERVER_ERROR_MESSAGE
