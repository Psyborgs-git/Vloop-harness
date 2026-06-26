"""Agent routes: CRUD, validate, templates."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any
from urllib.parse import unquote

from cp.handlers.router import register
from cp.http_responders import write_json
from cp.http_utils import require_method, split_segments

# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


def _handle_templates(
    handler: Any, method: str, _path: str, _query: Any, _body: Any, runtime: Any
) -> None:
    """GET /api/v1/agents/templates"""
    require_method(method, {"GET"})
    write_json(handler, {"agentTemplates": runtime.list_agent_templates()})


# ---------------------------------------------------------------------------
# Collection  /api/v1/agents
# ---------------------------------------------------------------------------


def _handle_agents(
    handler: Any, method: str, _path: str, _query: Any, body: Any, runtime: Any
) -> None:
    if method == "GET":
        write_json(handler, {"agents": runtime.list_agents()})
    elif method == "POST":
        agent = runtime.save_agent(body)
        write_json(handler, {"agent": agent}, status=HTTPStatus.CREATED)
    else:
        require_method(method, {"GET", "POST"})


# ---------------------------------------------------------------------------
# Validation shortcut  /api/v1/agents/validate
# ---------------------------------------------------------------------------


def _handle_validate(
    handler: Any, method: str, _path: str, _query: Any, body: Any, runtime: Any
) -> None:
    """POST /api/v1/agents/validate"""
    require_method(method, {"POST"})
    write_json(handler, runtime.validate_agent(body))


# ---------------------------------------------------------------------------
# Singleton  /api/v1/agents/{id}
# ---------------------------------------------------------------------------


def _handle_agent(
    handler: Any, method: str, _path: str, _query: Any, body: Any, runtime: Any
) -> None:
    segments = split_segments(_path)
    agent_id = unquote(segments[3])

    if method == "GET":
        agent = runtime.get_agent(agent_id)
        if agent is None:
            raise KeyError(f"agent `{agent_id}` was not found")
        write_json(handler, {"agent": agent})
    elif method in {"PUT", "PATCH", "POST"}:
        agent = runtime.save_agent(body, agent_id)
        write_json(handler, {"agent": agent})
    elif method == "DELETE":
        runtime.delete_agent(agent_id)
        write_json(handler, {"ok": True, "agentId": agent_id})
    else:
        require_method(method, {"GET", "PUT", "PATCH", "POST", "DELETE"})


# ---------------------------------------------------------------------------
# Sub-resources  /api/v1/agents/{id}/{action}
# ---------------------------------------------------------------------------


def _handle_agent_action(
    handler: Any, method: str, _path: str, _query: Any, body: Any, runtime: Any
) -> None:
    segments = split_segments(_path)
    agent_id = unquote(segments[3])
    suffix = segments[4]

    if suffix == "validate":
        require_method(method, {"POST"})
        write_json(handler, runtime.validate_agent(body, agent_id))
    elif suffix == "invoke":
        require_method(method, {"POST"})
        invocation = runtime.invoke_agent(agent_id, body)
        write_json(handler, {"invocation": invocation}, status=HTTPStatus.ACCEPTED)
    elif suffix == "invocations":
        if method == "GET":
            write_json(handler, {"invocations": runtime.list_invocations(agent_id)})
        elif method == "POST":
            invocation = runtime.invoke_agent(agent_id, body)
            write_json(handler, {"invocation": invocation}, status=HTTPStatus.ACCEPTED)
        else:
            require_method(method, {"GET", "POST"})
    else:
        raise KeyError(f"agent action `{suffix}` is not supported")


# -- registration ------------------------------------------------------------

register("*", ("api", "v1", "agents", "templates"), _handle_templates)
register("*", ("api", "v1", "agents"), _handle_agents)
register("*", ("api", "v1", "agents", "validate"), _handle_validate)
register("*", ("api", "v1", "agents", "*"), _handle_agent)
register("*", ("api", "v1", "agents", "*", "*"), _handle_agent_action)
