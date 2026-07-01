"""Workflow routes: create/validate definitions, run lifecycle, and templates.

Routes are mounted under ``/api/v1/workflows`` (definitions + runs starting) and
``/api/v1/workflow-runs`` (run observation/cancel/retry). They delegate to the
Planner, DAG_Executor, and workflow template catalog through runtime accessor
methods (wired in a later task — see task 30.10):

Definitions & validation
* ``GET  /api/v1/workflows``              → list persisted Workflow_Definitions
* ``POST /api/v1/workflows``              → validate via ``build_dag`` and persist
                                            **only** on success, returning the new
                                            id only then (Requirement 1.4)
* ``POST /api/v1/workflows/validate``     → validate a definition without
                                            persisting or assigning an id; pure,
                                            side-effect free (Requirements 1.4, 1.5)
* ``GET  /api/v1/workflows/{id}``         → fetch a persisted Workflow_Definition

Templates (Requirement 20.2)
* ``GET  /api/v1/workflows/templates``        → list reusable Workflow templates
* ``GET  /api/v1/workflows/templates/{id}``   → fetch one template
* ``POST /api/v1/workflows/templates/{id}``   → instantiate a template into a new,
                                                validated+persisted Workflow

Runs (Requirements 20.1, 4.x)
* ``GET  /api/v1/workflows/{id}/runs``        → list runs for a Workflow_Definition
* ``POST /api/v1/workflows/{id}/runs``        → start a Workflow_Run (Req 3.1, 20.1)
* ``GET  /api/v1/workflow-runs/{runId}``      → observe state + step states + events
                                                (Requirement 4.5)
* ``POST /api/v1/workflow-runs/{runId}/cancel`` → cancel a run (Requirement 4.2)
* ``POST /api/v1/workflow-runs/{runId}/retry``  → retry a failed run (Requirement 4.4)

Handlers follow the conventions in :mod:`cp.handlers.agents` and
:mod:`cp.handlers.schedules`: each receives
``(handler, method, path, query, body, runtime)``, validates the method with
:func:`~cp.http_utils.require_method`, and responds with
:func:`~cp.http_responders.write_json`. A definition rejected by the Planner
raises a ``ValueError`` (validation error) from the runtime, which the HTTP shell
maps to ``400 Bad Request`` while leaving the definition unpersisted and without
an id (Requirements 1.2, 1.3, 1.4).
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any
from urllib.parse import unquote

from cp.handlers.router import register
from cp.http_responders import write_json
from cp.http_utils import require_method, split_segments

# ---------------------------------------------------------------------------
# Validation shortcut  /api/v1/workflows/validate
# ---------------------------------------------------------------------------


def _handle_validate(
    handler: Any, method: str, _path: str, _query: Any, body: Any, runtime: Any
) -> None:
    """POST /api/v1/workflows/validate — pure validation, no persistence.

    Validation never persists or assigns an id (Requirements 1.4, 1.5); it
    returns the problems (if any) found by the Planner.
    """
    require_method(method, {"POST"})
    write_json(handler, runtime.validate_workflow(body))


# ---------------------------------------------------------------------------
# Template catalog  /api/v1/workflows/templates
# ---------------------------------------------------------------------------


def _handle_templates(
    handler: Any, method: str, _path: str, _query: Any, _body: Any, runtime: Any
) -> None:
    """GET /api/v1/workflows/templates — list reusable templates (Req 20.2)."""
    require_method(method, {"GET"})
    write_json(handler, {"workflowTemplates": runtime.list_workflow_templates()})


def _handle_template(
    handler: Any, method: str, _path: str, _query: Any, body: Any, runtime: Any
) -> None:
    """GET fetches a template; POST instantiates it into a Workflow (Req 20.2)."""
    segments = split_segments(_path)
    template_id = unquote(segments[4])

    if method == "GET":
        template = runtime.get_workflow_template(template_id)
        if template is None:
            raise KeyError(f"workflow template `{template_id}` was not found")
        write_json(handler, {"workflowTemplate": template})
    elif method == "POST":
        # Instantiating persists a validated Workflow_Definition (only on a
        # successful build_dag), so the new id is returned only then (Req 1.4).
        workflow = runtime.instantiate_workflow_template(template_id, body)
        write_json(handler, {"workflow": workflow}, status=HTTPStatus.CREATED)
    else:
        require_method(method, {"GET", "POST"})


# ---------------------------------------------------------------------------
# Collection  /api/v1/workflows
# ---------------------------------------------------------------------------


def _handle_workflows(
    handler: Any, method: str, _path: str, _query: Any, body: Any, runtime: Any
) -> None:
    """GET lists Workflow_Definitions; POST creates one (Requirement 1.4)."""
    if method == "GET":
        write_json(handler, {"workflows": runtime.list_workflows()})
    elif method == "POST":
        # The runtime compiles the definition via the Planner's build_dag and
        # persists it (assigning a unique id) only when validation succeeds;
        # an invalid definition raises and is surfaced as 400 with no id
        # assigned (Requirements 1.2, 1.3, 1.4).
        workflow = runtime.create_workflow(body)
        write_json(handler, {"workflow": workflow}, status=HTTPStatus.CREATED)
    else:
        require_method(method, {"GET", "POST"})


# ---------------------------------------------------------------------------
# Singleton  /api/v1/workflows/{id}
# ---------------------------------------------------------------------------


def _handle_workflow(
    handler: Any, method: str, _path: str, _query: Any, _body: Any, runtime: Any
) -> None:
    """GET /api/v1/workflows/{id} — fetch a persisted Workflow_Definition."""
    segments = split_segments(_path)
    workflow_id = unquote(segments[3])

    if method == "GET":
        workflow = runtime.get_workflow(workflow_id)
        if workflow is None:
            raise KeyError(f"workflow `{workflow_id}` was not found")
        write_json(handler, {"workflow": workflow})
    else:
        require_method(method, {"GET"})


# ---------------------------------------------------------------------------
# Sub-resources  /api/v1/workflows/{id}/{action}
# ---------------------------------------------------------------------------


def _handle_workflow_action(
    handler: Any, method: str, _path: str, _query: Any, body: Any, runtime: Any
) -> None:
    """POST /{id}/runs starts a run; GET /{id}/runs lists runs (Req 3.1, 20.1)."""
    segments = split_segments(_path)
    workflow_id = unquote(segments[3])
    suffix = segments[4]

    if suffix == "runs":
        if method == "POST":
            run = runtime.start_workflow_run(workflow_id, body)
            write_json(handler, {"run": run}, status=HTTPStatus.ACCEPTED)
        elif method == "GET":
            write_json(handler, {"runs": runtime.list_workflow_runs(workflow_id)})
        else:
            require_method(method, {"GET", "POST"})
    else:
        raise KeyError(f"workflow action `{suffix}` is not supported")


# ---------------------------------------------------------------------------
# Run observation  /api/v1/workflow-runs/{runId}
# ---------------------------------------------------------------------------


def _handle_run(
    handler: Any, method: str, _path: str, _query: Any, _body: Any, runtime: Any
) -> None:
    """GET /api/v1/workflow-runs/{runId} — state, step states, events (Req 4.5)."""
    require_method(method, {"GET"})
    segments = split_segments(_path)
    run_id = unquote(segments[3])
    write_json(handler, runtime.get_workflow_run(run_id))


# ---------------------------------------------------------------------------
# Run actions  /api/v1/workflow-runs/{runId}/{action}
# ---------------------------------------------------------------------------


def _handle_run_action(
    handler: Any, method: str, _path: str, _query: Any, _body: Any, runtime: Any
) -> None:
    """POST /{runId}/cancel and /{runId}/retry (Requirements 4.2, 4.4)."""
    segments = split_segments(_path)
    run_id = unquote(segments[3])
    suffix = segments[4]

    if suffix == "cancel":
        require_method(method, {"POST"})
        write_json(handler, {"run": runtime.cancel_workflow_run(run_id)})
    elif suffix == "retry":
        require_method(method, {"POST"})
        write_json(handler, {"run": runtime.retry_workflow_run(run_id)})
    else:
        raise KeyError(f"workflow run action `{suffix}` is not supported")


# -- registration ------------------------------------------------------------
# Static segments (validate/templates) are registered before the wildcard
# singleton/action patterns so they match first (router dispatches in order).

register("*", ("api", "v1", "workflows", "validate"), _handle_validate)
register("*", ("api", "v1", "workflows", "templates"), _handle_templates)
register("*", ("api", "v1", "workflows", "templates", "*"), _handle_template)
register("*", ("api", "v1", "workflows"), _handle_workflows)
register("*", ("api", "v1", "workflows", "*"), _handle_workflow)
register("*", ("api", "v1", "workflows", "*", "*"), _handle_workflow_action)
register("*", ("api", "v1", "workflow-runs", "*"), _handle_run)
register("*", ("api", "v1", "workflow-runs", "*", "*"), _handle_run_action)
