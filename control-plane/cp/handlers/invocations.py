"""Invocation routes: list, get, events, and inline invoke."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any
from urllib.parse import unquote

from cp.handlers.router import register
from cp.http_responders import write_json
from cp.http_utils import (
    optional_query_value,
    require_method,
    required_string,
    split_segments,
)

# ---------------------------------------------------------------------------
# Collection  /api/v1/invocations
# ---------------------------------------------------------------------------


def _handle_invocations(
    handler: Any, method: str, _path: str, query: Any, body: Any, runtime: Any
) -> None:
    """GET /api/v1/invocations  (also POST for inline invoke)."""
    if method == "GET":
        agent_id = optional_query_value(query, "agentId", "agent_id")
        write_json(handler, {"invocations": runtime.list_invocations(agent_id)})
    elif method == "POST":
        agent_id = required_string(body, "agentId", "agent_id")
        invocation = runtime.invoke_agent(agent_id, body)
        write_json(handler, {"invocation": invocation}, status=HTTPStatus.ACCEPTED)
    else:
        require_method(method, {"GET", "POST"})


# ---------------------------------------------------------------------------
# Singleton  /api/v1/invocations/{id}
# ---------------------------------------------------------------------------


def _handle_invocation(
    handler: Any, method: str, _path: str, _query: Any, _body: Any, runtime: Any
) -> None:
    """GET /api/v1/invocations/{id}"""
    require_method(method, {"GET"})
    segments = split_segments(_path)
    invocation_id = unquote(segments[3])
    invocation = runtime.get_invocation(invocation_id)
    if invocation is None:
        raise KeyError(f"invocation `{invocation_id}` was not found")
    write_json(handler, {"invocation": invocation})


# ---------------------------------------------------------------------------
# Sub-resource  /api/v1/invocations/{id}/events
# ---------------------------------------------------------------------------


def _handle_invocation_events(
    handler: Any, method: str, _path: str, _query: Any, _body: Any, runtime: Any
) -> None:
    """GET /api/v1/invocations/{id}/events"""
    require_method(method, {"GET"})
    segments = split_segments(_path)
    invocation_id = unquote(segments[3])
    write_json(
        handler,
        {
            "events": runtime.get_invocation_events(invocation_id),
            "invocationId": invocation_id,
        },
    )


# ---------------------------------------------------------------------------
# Legacy  /api/v1/invocation-events  (query-param style)
# ---------------------------------------------------------------------------


def _handle_invocation_events_query(
    handler: Any, method: str, _path: str, query: Any, _body: Any, runtime: Any
) -> None:
    """GET /api/v1/invocation-events?invocationId=..."""
    require_method(method, {"GET"})
    invocation_id = optional_query_value(query, "invocationId", "invocation_id")
    if not invocation_id:
        raise ValueError("query parameter `invocationId` is required")
    write_json(
        handler,
        {
            "events": runtime.get_invocation_events(invocation_id),
            "invocationId": invocation_id,
        },
    )


# -- registration ------------------------------------------------------------

register("*", ("api", "v1", "invocations"), _handle_invocations)
register("*", ("api", "v1", "invocations", "__id__"), _handle_invocation)
register(
    "*", ("api", "v1", "invocations", "__id__", "events"), _handle_invocation_events
)
register("*", ("api", "v1", "invocation-events"), _handle_invocation_events_query)
