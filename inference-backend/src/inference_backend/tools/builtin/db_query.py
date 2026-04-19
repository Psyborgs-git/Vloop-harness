"""db_query tool — query the harness-core internal REST DB endpoint."""
from __future__ import annotations

import httpx
from ..registry import tool
from ...config import HARNESS_CORE_URL


@tool("db_query")
def db_query(sql: str, params: list | None = None) -> dict:
    """Execute a SQL query against the harness-core SQLite database."""
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                f"{HARNESS_CORE_URL}/api/db/query",
                json={"sql": sql, "params": params or []},
            )
            return resp.json()
    except Exception as exc:
        return {"error": str(exc)}
