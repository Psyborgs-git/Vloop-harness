"""http_request tool — make HTTP requests (GET/POST)."""
from __future__ import annotations

import httpx
from ..registry import tool


@tool("http_request")
def http_request(
    url: str,
    method: str = "GET",
    json: dict | None = None,
    headers: dict | None = None,
    timeout: float = 10.0,
) -> dict:
    """Perform an HTTP request and return status + body."""
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.request(method.upper(), url, json=json, headers=headers)
            try:
                body = resp.json()
            except Exception:
                body = resp.text
            return {"status_code": resp.status_code, "body": body}
    except Exception as exc:
        return {"error": str(exc)}
