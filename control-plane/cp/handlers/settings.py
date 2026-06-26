"""Settings routes: database configuration and connectivity test."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

from core.database import create_database
from cp.handlers.router import register
from cp.http_responders import write_json
from cp.http_utils import clean_exception_message, require_method

# ---------------------------------------------------------------------------
# GET / PUT  /api/v1/settings/database
# ---------------------------------------------------------------------------


def _handle_settings_database(
    handler: Any, method: str, _path: str, _query: Any, body: Any, runtime: Any
) -> None:
    if method == "GET":
        write_json(
            handler,
            {
                "databaseUrl": runtime.config.database_url or "",
                "vectorDbUrl": runtime.config.vector_db_url or "",
                "activeBackend": runtime.db.__class__.__name__,
                "vectorStoreActive": (
                    runtime.vector_store.__class__.__name__
                    if runtime.vector_store
                    else "none"
                ),
            },
        )
    elif method in ("POST", "PUT"):
        db_url = body.get("databaseUrl", "")
        vec_url = body.get("vectorDbUrl", "")
        runtime.config.database_url = db_url or None
        runtime.config.vector_db_url = vec_url or None
        write_json(
            handler,
            {
                "ok": True,
                "message": (
                    "Database config updated. "
                    "Restart the control plane for changes to take effect."
                ),
            },
        )
    else:
        require_method(method, {"GET", "POST", "PUT"})


# ---------------------------------------------------------------------------
# POST  /api/v1/settings/database/test
# ---------------------------------------------------------------------------


def _handle_settings_database_test(
    handler: Any, method: str, _path: str, _query: Any, body: Any, runtime: Any
) -> None:
    """POST /api/v1/settings/database/test"""
    require_method(method, {"POST"})
    try:
        test_db = create_database(body.get("databaseUrl") or None)
        test_db.fetch_one("SELECT 1")
        test_db.close()
        write_json(handler, {"ok": True, "message": "Connection successful"})
    except Exception as exc:
        write_json(
            handler,
            {
                "ok": False,
                "message": f"Connection failed: {clean_exception_message(exc)}",
            },
            status=HTTPStatus.BAD_REQUEST,
        )


# -- registration ------------------------------------------------------------

register("*", ("api", "v1", "settings", "database"), _handle_settings_database)
register(
    "*", ("api", "v1", "settings", "database", "test"), _handle_settings_database_test
)
