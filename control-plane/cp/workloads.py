"""Workload management — gRPC pass-through to the kernel."""

from __future__ import annotations

import logging
from typing import Any

LOGGER = logging.getLogger("vloop.control_plane.workloads")


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not value or not isinstance(value, str):
        raise ValueError(f"missing required string field `{key}`")
    return value


def _workload_to_dict(record: Any) -> dict[str, Any]:
    """Convert a gRPC WorkloadRecord proto to a JSON-safe dict."""
    spec = record.spec
    workload_class = getattr(record, "class", 0)
    workload_state = getattr(record, "state", 0)
    class_map = {
        0: "unspecified",
        1: "harness",
        2: "worker",
        3: "preview",
        4: "service",
    }
    state_map = {
        0: "unspecified",
        1: "created",
        2: "prepared",
        3: "starting",
        4: "running",
        5: "completed",
        6: "failed",
        7: "cancelling",
        8: "cancelled",
        9: "garbage_collected",
    }
    return {
        "workloadId": record.workload_id,
        "class": class_map.get(workload_class, "unspecified"),
        "state": state_map.get(workload_state, "unspecified"),
        "spec": {
            "image": spec.image if spec else "",
            "command": list(spec.command) if spec and spec.command else [],
            "ports": list(spec.ports) if spec and spec.ports else [],
            "environment": dict(spec.environment) if spec and spec.environment else {},
        },
        "createdAtUnixMs": record.created_at_unix_ms,
        "updatedAtUnixMs": record.updated_at_unix_ms,
        "exitCode": record.exit_code,
        "terminationReason": record.termination_reason,
        "exposedPorts": list(record.exposed_ports),
        "previewUrl": record.preview_url,
    }


# -- async workload operations (mixed into ControlPlaneRuntime) ------------


async def _list_workloads_async(runtime: Any) -> list[dict[str, Any]]:
    if runtime._workload_stub is None:
        return []
    try:
        response = await runtime._workload_stub.ListWorkloads(
            runtime.kernel_pb2.ListWorkloadsRequest(),
            metadata=runtime._metadata(include_session=True),
            timeout=runtime.config.rpc_timeout_seconds,
        )
        workloads = [_workload_to_dict(w) for w in response.workloads]
        runtime._workload_cache = {w["workloadId"]: w for w in workloads}
        return workloads
    except Exception as exc:
        LOGGER.warning("failed to list workloads: %s", exc)
        return []


async def _create_workload_async(
    runtime: Any, payload: dict[str, Any]
) -> dict[str, Any]:
    if runtime._workload_stub is None:
        raise RuntimeError("kernel workload stub is not connected")
    image = _required_string(payload, "image")
    command = payload.get("command", [])
    if isinstance(command, str):
        command = [command]
    ports = payload.get("ports", [])
    environment = payload.get("environment", {})
    class_name = payload.get("class", "HARNESS")
    class_enum = getattr(
        runtime.kernel_pb2,
        f"WORKLOAD_CLASS_{class_name.upper()}",
        runtime.kernel_pb2.WORKLOAD_CLASS_HARNESS,
    )

    spec = runtime.kernel_pb2.WorkloadSpec(
        image=image,
        command=command if isinstance(command, list) else list(command),
        ports=ports,
        environment=environment,
    )
    setattr(spec, "class", class_enum)
    req = runtime.kernel_pb2.CreateWorkloadRequest(spec=spec)
    response = await runtime._workload_stub.CreateWorkload(
        req,
        metadata=runtime._metadata(include_session=True),
        timeout=runtime.config.rpc_timeout_seconds,
    )
    workload = _workload_to_dict(response.workload)
    runtime._workload_cache[workload["workloadId"]] = workload
    return workload


async def _get_workload_async(runtime: Any, workload_id: str) -> dict[str, Any]:
    if runtime._workload_stub is None:
        raise RuntimeError("kernel workload stub is not connected")
    req = runtime.kernel_pb2.GetWorkloadRequest(workload_id=workload_id)
    response = await runtime._workload_stub.GetWorkload(
        req,
        metadata=runtime._metadata(include_session=True),
        timeout=runtime.config.rpc_timeout_seconds,
    )
    workload = _workload_to_dict(response.workload)
    runtime._workload_cache[workload["workloadId"]] = workload
    return workload


async def _start_workload_async(runtime: Any, workload_id: str) -> dict[str, Any]:
    if runtime._workload_stub is None:
        raise RuntimeError("kernel workload stub is not connected")
    req = runtime.kernel_pb2.StartWorkloadRequest(workload_id=workload_id)
    response = await runtime._workload_stub.StartWorkload(
        req,
        metadata=runtime._metadata(include_session=True),
        timeout=runtime.config.rpc_timeout_seconds,
    )
    workload = _workload_to_dict(response.workload)
    runtime._workload_cache[workload["workloadId"]] = workload
    return workload


async def _stop_workload_async(runtime: Any, workload_id: str) -> dict[str, Any]:
    if runtime._workload_stub is None:
        raise RuntimeError("kernel workload stub is not connected")
    req = runtime.kernel_pb2.StopWorkloadRequest(workload_id=workload_id)
    response = await runtime._workload_stub.StopWorkload(
        req,
        metadata=runtime._metadata(include_session=True),
        timeout=runtime.config.rpc_timeout_seconds,
    )
    workload = _workload_to_dict(response.workload)
    runtime._workload_cache[workload["workloadId"]] = workload
    return workload


async def _get_workload_logs_async(runtime: Any, workload_id: str) -> dict[str, Any]:
    if runtime._workload_stub is None:
        return {"workloadId": workload_id, "logs": []}
    try:
        stream = runtime._workload_stub.WatchWorkloadLogs(
            runtime.kernel_pb2.WatchWorkloadLogsRequest(workload_id=workload_id),
            metadata=runtime._metadata(include_session=True),
        )
        lines: list[dict[str, Any]] = []
        async for log_line in stream:
            lines.append(
                {
                    "stream": log_line.stream,
                    "line": log_line.line,
                    "timestampUnixMs": log_line.timestamp_unix_ms,
                }
            )
        return {"workloadId": workload_id, "logs": lines}
    except Exception as exc:
        LOGGER.warning("failed to read workload logs for %s: %s", workload_id, exc)
        return {"workloadId": workload_id, "logs": []}
