"""Approval routes: list a run's pending approvals and submit decisions.

These routes expose the Approval_Manager (``core/approval_manager.py``) over
HTTP so the Frontend approvals view can surface Approval_Checkpoints and submit
an approve/reject decision (Requirements 8.2, 8.3, 8.4, 20.4):

* ``GET  /api/v1/workflow-runs/{run_id}/approvals`` lists the checkpoints in a
  Workflow_Run currently awaiting a decision, reconstructed from persistence so
  it is restart-safe (Requirement 8.5). Each entry carries the checkpoint
  ``context`` that was streamed with the ``approval.required`` event
  (Requirement 8.2).
* ``POST /api/v1/workflow-runs/{run_id}/approvals/{step_id}/approve`` records the
  (optionally edited) decision and resumes the run from the checkpoint
  (Requirement 8.3). Optional body: ``{"edits": {...}}``.
* ``POST /api/v1/workflow-runs/{run_id}/approvals/{step_id}/reject`` drives the
  run to the terminal ``rejected`` state and skips the checkpoint's dependents
  (Requirement 8.4). Optional body: ``{"reason": "..."}``.

The handlers reach the Approval_Manager through ``runtime`` accessor methods
(``runtime.pending_approvals`` / ``runtime.approve_checkpoint`` /
``runtime.reject_checkpoint``); the accessors delegate to the Approval_Manager
and return the refreshed run view.

Registration note: the pending-listing pattern
``("api", "v1", "workflow-runs", "*", "approvals")`` positionally overlaps the
generic run-action pattern ``("api", "v1", "workflow-runs", "*", "*")`` in
``cp/handlers/workflows.py``. The router dispatches in registration order, so
this module MUST be imported before ``cp.handlers.workflows`` (see
``cp/handlers/__init__.py``) for the literal ``approvals`` segment to win.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import unquote

from cp.handlers.router import register
from cp.http_responders import write_json
from cp.http_utils import require_method, split_segments

# ---------------------------------------------------------------------------
# Listing  /api/v1/workflow-runs/{run_id}/approvals   (Requirements 8.2, 8.5)
# ---------------------------------------------------------------------------


def _handle_run_approvals(
    handler: Any, method: str, _path: str, _query: Any, _body: Any, runtime: Any
) -> None:
    """GET /api/v1/workflow-runs/{run_id}/approvals"""
    require_method(method, {"GET"})
    segments = split_segments(_path)
    run_id = unquote(segments[3])
    write_json(
        handler,
        {
            "approvals": runtime.pending_approvals(run_id),
            "runId": run_id,
        },
    )


# ---------------------------------------------------------------------------
# Decision  /api/v1/workflow-runs/{run_id}/approvals/{step_id}/{decision}
# (Requirements 8.3, 8.4)
# ---------------------------------------------------------------------------


def _handle_approval_decision(
    handler: Any, method: str, _path: str, _query: Any, body: Any, runtime: Any
) -> None:
    """POST /api/v1/workflow-runs/{run_id}/approvals/{step_id}/{approve|reject}"""
    require_method(method, {"POST"})
    segments = split_segments(_path)
    run_id = unquote(segments[3])
    # segments[4] is the literal "approvals" mount segment.
    step_id = unquote(segments[5])
    decision = segments[6]
    payload = body or {}

    if decision == "approve":
        edits = payload.get("edits")
        run = runtime.approve_checkpoint(run_id, step_id, edits)
        write_json(handler, {"run": run})
    elif decision == "reject":
        reason = str(payload.get("reason") or "")
        run = runtime.reject_checkpoint(run_id, step_id, reason)
        write_json(handler, {"run": run})
    else:
        raise KeyError(f"approval decision `{decision}` is not supported")


# -- registration ------------------------------------------------------------
# The pending-listing pattern overlaps workflows.py's run-action wildcard, so
# this module is imported first (cp/handlers/__init__.py) to match on the
# literal ``approvals`` segment before the wildcard is tried.

register(
    "*", ("api", "v1", "workflow-runs", "*", "approvals"), _handle_run_approvals
)
register(
    "*",
    ("api", "v1", "workflow-runs", "*", "approvals", "*", "*"),
    _handle_approval_decision,
)
