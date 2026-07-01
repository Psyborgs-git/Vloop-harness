"""HTTP request handler — dispatch, API routing, and static file serving."""

from __future__ import annotations

import logging
import sqlite3
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import parse_qs, urlsplit

from cp.handlers import route  # the central router
from cp.http_responders import log_internal_error, write_error_json
from cp.http_utils import (
    clean_exception_message,
    read_json_body,
    serve_frontend_asset,
)

LOGGER = logging.getLogger("vloop.control_plane.http")


def handler_factory(runtime: Any):
    """Create a ControlPlaneHandler class bound to the given runtime."""

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

        # -- dispatch ----------------------------------------------------

        def _dispatch(self, method: str) -> None:
            url = urlsplit(self.path)
            path = url.path or "/"
            query = parse_qs(url.query, keep_blank_values=True)

            try:
                # /api/* → route to handler sub-modules
                if path.startswith("/api/"):
                    body = (
                        read_json_body(self)
                        if method in {"POST", "PUT", "PATCH", "DELETE"}
                        else {}
                    )
                    route(self, method, path, query, body, runtime)
                    return

                # non-/api GET → try static assets
                if method == "GET":
                    serve_frontend_asset(self, runtime, path)
                    return

                write_error_json(
                    self,
                    HTTPStatus.METHOD_NOT_ALLOWED,
                    f"method {method} is not supported for {path}",
                )
            except Exception as exc:
                self._handle_exception(exc)

        # -- exception handling ------------------------------------------

        def _handle_exception(self, exc: Exception) -> None:
            from cp.http_api import MethodNotAllowedError

            if isinstance(exc, MethodNotAllowedError):
                write_error_json(
                    self,
                    HTTPStatus.METHOD_NOT_ALLOWED,
                    str(exc),
                    extra={"allowed": sorted(exc.allowed)},
                )
                return
            if isinstance(exc, KeyError):
                write_error_json(
                    self, HTTPStatus.NOT_FOUND, clean_exception_message(exc)
                )
                return
            if isinstance(exc, ValueError):
                write_error_json(
                    self, HTTPStatus.BAD_REQUEST, clean_exception_message(exc)
                )
                return
            if isinstance(exc, sqlite3.IntegrityError):
                write_error_json(
                    self, HTTPStatus.CONFLICT, clean_exception_message(exc)
                )
                return
            if isinstance(exc, RuntimeError):
                write_error_json(
                    self, HTTPStatus.CONFLICT, clean_exception_message(exc)
                )
                return

            # Unexpected / server-side failure. Retain full detail (with
            # traceback, secret-redacted) in the server log, but return only a
            # generic non-technical message to the user (Requirement 20.3). The
            # generic substitution is enforced centrally by write_error_json.
            log_internal_error(
                exc,
                logger=LOGGER,
                context="control-plane HTTP request failed",
            )
            write_error_json(
                self,
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "internal control-plane error",
            )

    return ControlPlaneHandler
