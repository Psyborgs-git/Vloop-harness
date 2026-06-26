"""Workload routes: list, create, get, start, stop, delete, logs."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any
from urllib.parse import unquote

from cp.handlers.router import register
from cp.http_responders import write_json
from cp.http_utils import require_method, split_segments

# ---------------------------------------------------------------------------
# Collection  /api/v1/workloads
# ---------------------------------------------------------------------------


def _handle_workloads(
    handler: Any, method: str, _path: str, _query: Any, body: Any, runtime: Any
) -> None:
    if method == "GET":
        write_json(handler, runtime.list_workloads())
    elif method == "POST":
        workload = runtime.create_workload(body)
        write_json(handler, {"workload": workload}, status=HTTPStatus.CREATED)
    else:
        require_method(method, {"GET", "POST"})


# ---------------------------------------------------------------------------
# Singleton  /api/v1/workloads/{id}
# ---------------------------------------------------------------------------


def _handle_workload(
    handler: Any, method: str, _path: str, _query: Any, body: Any, runtime: Any
) -> None:
    segments = split_segments(_path)
    workload_id = unquote(segments[3])

    if method == "GET":
        write_json(handler, runtime.get_workload(workload_id))
    elif method == "PUT":
        # PUT on workloads/{id} was not handled in the original code.
        # We match that behaviour by raising KeyError → 404.
        raise KeyError(f"PUT is not supported for workload `{workload_id}`")
    elif method == "DELETE":
        runtime.remove_workload(workload_id)
        write_json(handler, {"ok": True, "workloadId": workload_id})
    else:
        require_method(method, {"GET", "DELETE"})


# ---------------------------------------------------------------------------
# Sub-resources  /api/v1/workloads/{id}/{action}
# ---------------------------------------------------------------------------


def _handle_workload_action(
    handler: Any, method: str, _path: str, _query: Any, body: Any, runtime: Any
) -> None:
    segments = split_segments(_path)
    workload_id = unquote(segments[3])
    suffix = segments[4]

    if suffix == "start":
        require_method(method, {"POST"})
        workload = runtime.start_workload(workload_id)
        write_json(handler, {"workload": workload})
    elif suffix == "stop":
        require_method(method, {"POST"})
        workload = runtime.stop_workload(workload_id)
        write_json(handler, {"workload": workload})
    elif suffix == "logs":
        require_method(method, {"GET"})
        write_json(handler, runtime.get_workload_logs(workload_id))
    else:
        raise KeyError(f"workload action `{suffix}` is not supported")


# -- registration ------------------------------------------------------------

register("*", ("api", "v1", "workloads"), _handle_workloads)
register("*", ("api", "v1", "workloads", "*"), _handle_workload)
register("*", ("api", "v1", "workloads", "*", "*"), _handle_workload_action)
