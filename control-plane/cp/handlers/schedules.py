"""Scheduled-task routes: create, pause, resume, and list (Requirement 14).

Routes are mounted under ``/api/v1/schedules`` and delegate to the Scheduler via
the runtime accessor methods (wired in a later task):

* ``GET  /api/v1/schedules``               → list Scheduled_Tasks (Req 14.1)
* ``POST /api/v1/schedules``               → create a Scheduled_Task in either an
                                              ``active`` or ``paused`` state (Req 14.1)
* ``POST /api/v1/schedules/{id}/pause``    → pause a Scheduled_Task (Req 14.3)
* ``POST /api/v1/schedules/{id}/resume``   → resume a Scheduled_Task (Req 14.3)

Handlers follow the conventions in :mod:`cp.handlers.agents` and
:mod:`cp.handlers.providers`: each receives
``(handler, method, path, query, body, runtime)``, validates the method with
:func:`~cp.http_utils.require_method`, and responds with
:func:`~cp.http_responders.write_json`. Invalid cron expressions raise
``CronParseError`` (a ``ValueError``) from the Scheduler, which the HTTP shell
maps to ``400 Bad Request`` (Requirement 14.5).
"""

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

# Scheduled_Task lifecycle states accepted on creation.
_STATE_ACTIVE = "active"
_STATE_PAUSED = "paused"
_VALID_STATES = frozenset({_STATE_ACTIVE, _STATE_PAUSED})


# ---------------------------------------------------------------------------
# Collection  /api/v1/schedules
# ---------------------------------------------------------------------------


def _handle_schedules(
    handler: Any, method: str, _path: str, query: Any, body: Any, runtime: Any
) -> None:
    """GET lists Scheduled_Tasks; POST creates one (Requirement 14.1)."""
    if method == "GET":
        definition_id = optional_query_value(query, "definitionId", "definition_id")
        tasks = runtime.list_scheduled_tasks(definition_id=definition_id)
        write_json(handler, {"scheduledTasks": tasks})
    elif method == "POST":
        definition_id = required_string(body, "definitionId", "definition_id")
        cron_expression = required_string(
            body, "cronExpression", "cron_expression", "cron"
        )
        state = _coerce_state(body.get("state"))
        task = runtime.create_scheduled_task(
            definition_id,
            cron_expression,
            state=state,
        )
        write_json(handler, {"scheduledTask": task}, status=HTTPStatus.CREATED)
    else:
        require_method(method, {"GET", "POST"})


# ---------------------------------------------------------------------------
# Sub-resources  /api/v1/schedules/{id}/{action}
# ---------------------------------------------------------------------------


def _handle_schedule_action(
    handler: Any, method: str, _path: str, _query: Any, _body: Any, runtime: Any
) -> None:
    """POST /{id}/pause and POST /{id}/resume (Requirement 14.3)."""
    segments = split_segments(_path)
    task_id = unquote(segments[3])
    suffix = segments[4]

    if suffix == "pause":
        require_method(method, {"POST"})
        task = runtime.pause_scheduled_task(task_id)
        write_json(handler, {"scheduledTask": task})
    elif suffix == "resume":
        require_method(method, {"POST"})
        task = runtime.resume_scheduled_task(task_id)
        write_json(handler, {"scheduledTask": task})
    else:
        raise KeyError(f"schedule action `{suffix}` is not supported")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _coerce_state(raw: Any) -> str:
    """Normalize the optional creation state, defaulting to ``active``.

    A Scheduled_Task may be created ``active`` or ``paused`` (Requirement 14.1);
    any other value is rejected with a descriptive ``ValueError`` (→ 400).
    """
    if raw is None:
        return _STATE_ACTIVE
    state = str(raw).strip().lower()
    if state not in _VALID_STATES:
        raise ValueError(
            f"state must be one of {sorted(_VALID_STATES)}, got `{raw}`"
        )
    return state


# -- registration ------------------------------------------------------------

register("*", ("api", "v1", "schedules"), _handle_schedules)
register("*", ("api", "v1", "schedules", "*", "*"), _handle_schedule_action)
