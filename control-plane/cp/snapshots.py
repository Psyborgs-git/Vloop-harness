"""Snapshot methods for the control-plane runtime."""

from __future__ import annotations

import logging
from typing import Any

from cp.session import SessionSnapshot

LOGGER = logging.getLogger("vloop.control_plane")


# These functions are mixed into ControlPlaneRuntime dynamically or used
# as module-level helpers for snapshot assembly.


def build_health_snapshot(runtime: Any) -> dict[str, Any]:
    return {
        "status": runtime.status,
        "version": runtime.config.version,
        "kernel_endpoint": runtime.config.kernel_endpoint,
        "http_base_url": runtime.config.http_base_url()
        if runtime.config.serve_http
        else None,
        "shell_url": runtime.config.shell_url() if runtime.config.serve_http else None,
        "session_id": runtime.session_id,
        "last_error": runtime.last_error,
        "window": runtime.window_snapshot(),
    }


def build_session_snapshot(runtime: Any) -> dict[str, Any]:
    return SessionSnapshot(
        status=runtime.status,
        kernel_endpoint=runtime.config.kernel_endpoint,
        http_base_url=runtime.config.http_base_url()
        if runtime.config.serve_http
        else None,
        shell_url=runtime.config.shell_url() if runtime.config.serve_http else None,
        session_id=runtime.session_id,
        granted_scopes=list(runtime.granted_scopes),
        last_registered_at_unix_ms=runtime.last_registered_at_unix_ms,
        last_heartbeat_at_unix_ms=runtime.last_heartbeat_at_unix_ms,
        last_error=runtime.last_error,
        active_config=runtime.active_config.to_dict()
        if runtime.active_config
        else None,
    ).to_dict()


def build_event_snapshot(runtime: Any) -> dict[str, Any]:
    return runtime.event_router.snapshot()


def build_window_snapshot(runtime: Any) -> dict[str, Any]:
    return runtime.window_manager.snapshot().to_dict()


def build_system_snapshot(runtime: Any) -> dict[str, Any]:
    events = build_event_snapshot(runtime)
    return {
        "health": build_health_snapshot(runtime),
        "session": build_session_snapshot(runtime),
        "window": build_window_snapshot(runtime),
        "dependencies": runtime.dependency_snapshot(),
        "recentEvents": events.get("recent_events", []),
        "eventCount": events.get("event_count", 0),
    }


def build_dependency_snapshot(runtime: Any) -> dict[str, Any]:
    """Fetch live dependency status from the kernel via gRPC."""
    try:
        return runtime._run_on_loop(_dependency_snapshot_async(runtime))
    except Exception as exc:
        LOGGER.warning("failed to fetch kernel dependencies: %s", exc)
        return {"dependencies": [], "error": str(exc)}


async def _dependency_snapshot_async(runtime: Any) -> dict[str, Any]:
    if runtime._grpc_channel is None:
        return {"dependencies": [], "error": "gRPC channel is not connected"}
    deps_stub = runtime.kernel_pb2_grpc.KernelLifecycleStub(runtime._grpc_channel)
    response = await deps_stub.GetDependencies(
        runtime.kernel_pb2.GetDependenciesRequest(),
        metadata=runtime._metadata(include_session=True),
        timeout=runtime.config.rpc_timeout_seconds,
    )
    return {
        "dependencies": [
            {
                "name": dep.name,
                "state": runtime.kernel_pb2.DependencyState.Name(dep.state),
                "message": dep.message,
                "detectedVersion": dep.detected_version or None,
                "remediation": dep.remediation or None,
            }
            for dep in response.dependencies
        ],
    }


def build_bootstrap_payload(runtime: Any) -> dict[str, Any]:
    return {
        "providers": runtime.list_providers(),
        "agents": runtime.list_agents(),
        "invocations": runtime.list_invocations(),
        "providerCatalog": runtime.provider_catalog(),
        "agentTemplates": runtime.list_agent_templates(),
        "apiAvailable": True,
        "source": "bootstrap",
        "warning": None,
    }
