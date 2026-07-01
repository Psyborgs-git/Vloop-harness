"""Checkpoint routes: list a run's checkpoints and request rollback.

These routes expose the Checkpoint_Manager (``core/checkpoint_manager.py``) over
HTTP:

* ``GET  /api/v1/runs/{run_id}/checkpoints`` lists the Checkpoints recorded for a
  Workflow_Run (Requirement 13.3).
* ``POST /api/v1/checkpoints/{checkpoint_id}/rollback`` requests that the Kernel
  restore the workspace to a Checkpoint's snapshot (Requirement 13.2).

The handlers reach the Checkpoint_Manager through ``runtime`` accessor methods
(``runtime.list_checkpoints`` / ``runtime.restore_checkpoint``); runtime wiring
itself is handled separately (task 30.10).
"""

from __future__ import annotations

from typing import Any
from urllib.parse import unquote

from cp.handlers.router import register
from cp.http_responders import write_json
from cp.http_utils import require_method, split_segments

# ---------------------------------------------------------------------------
# Listing  /api/v1/runs/{run_id}/checkpoints   (Requirement 13.3)
# ---------------------------------------------------------------------------


def _handle_run_checkpoints(
    handler: Any, method: str, _path: str, _query: Any, _body: Any, runtime: Any
) -> None:
    """GET /api/v1/runs/{run_id}/checkpoints"""
    require_method(method, {"GET"})
    segments = split_segments(_path)
    run_id = unquote(segments[3])
    write_json(
        handler,
        {
            "checkpoints": runtime.list_checkpoints(run_id),
            "runId": run_id,
        },
    )


# ---------------------------------------------------------------------------
# Rollback  /api/v1/checkpoints/{checkpoint_id}/rollback   (Requirement 13.2)
# ---------------------------------------------------------------------------


def _handle_checkpoint_rollback(
    handler: Any, method: str, _path: str, _query: Any, _body: Any, runtime: Any
) -> None:
    """POST /api/v1/checkpoints/{checkpoint_id}/rollback"""
    require_method(method, {"POST"})
    segments = split_segments(_path)
    checkpoint_id = unquote(segments[3])
    suffix = segments[4]
    if suffix != "rollback":
        raise KeyError(f"checkpoint action `{suffix}` is not supported")
    checkpoint = runtime.restore_checkpoint(checkpoint_id)
    write_json(handler, {"checkpoint": checkpoint})


# -- registration ------------------------------------------------------------

register("*", ("api", "v1", "runs", "*", "checkpoints"), _handle_run_checkpoints)
register(
    "*", ("api", "v1", "checkpoints", "*", "rollback"), _handle_checkpoint_rollback
)
