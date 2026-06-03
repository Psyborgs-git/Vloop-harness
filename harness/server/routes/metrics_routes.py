"""REST routes for metrics and observability.

Endpoints
─────────
  GET /api/metrics — Get all metrics
  GET /api/metrics/{name} — Get specific metric
  POST /api/metrics/reset — Reset all metrics
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from harness.core.metrics import get_metrics_registry

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("")
async def get_metrics() -> dict[str, Any]:
    """Get all metrics from the registry."""
    registry = get_metrics_registry()
    return registry.get_all_metrics()


@router.get("/summary")
async def get_metrics_summary() -> dict[str, Any]:
    """Get a summary of key metrics."""
    registry = get_metrics_registry()
    all_metrics = registry.get_all_metrics()

    # Calculate summary statistics
    summary = {
        "total_counters": len(all_metrics.get("counters", [])),
        "total_gauges": len(all_metrics.get("gauges", [])),
        "total_histograms": len(all_metrics.get("histograms", [])),
        "key_metrics": {},
    }

    # Extract key metrics
    for counter in all_metrics.get("counters", []):
        if "tool_executions" in counter["name"] or "component_executions" in counter["name"]:
            summary["key_metrics"][counter["name"]] = counter["value"]

    for hist in all_metrics.get("histograms", []):
        if "duration" in hist["name"]:
            summary["key_metrics"][f"{hist['name']}_summary"] = hist["summary"]

    return summary


@router.post("/reset")
async def reset_metrics() -> dict[str, str]:
    """Reset all metrics in the registry."""
    registry = get_metrics_registry()
    registry.reset()
    return {"status": "reset"}


# ── Query tracing endpoints ───────────────────────────────────────────────────


@router.get("/queries/traces")
async def get_query_traces(limit: int = 50) -> list[dict[str, Any]]:
    """Get recent query traces."""
    from harness.data.query_tracer import get_query_tracer

    tracer = get_query_tracer()
    return tracer.get_recent_traces(limit)


@router.get("/queries/slow")
async def get_slow_queries(limit: int = 50) -> list[dict[str, Any]]:
    """Get slow queries."""
    from harness.data.query_tracer import get_query_tracer

    tracer = get_query_tracer()
    return tracer.get_slow_queries(limit)


@router.get("/queries/stats")
async def get_query_stats() -> list[dict[str, Any]]:
    """Get aggregated query statistics."""
    from harness.data.query_tracer import get_query_tracer

    tracer = get_query_tracer()
    return tracer.get_query_stats()


@router.post("/queries/reset")
async def reset_query_traces() -> dict[str, str]:
    """Reset all query traces and statistics."""
    from harness.data.query_tracer import get_query_tracer

    tracer = get_query_tracer()
    tracer.reset()
    return {"status": "reset"}


# ── Resource monitoring endpoints ────────────────────────────────────────────


@router.get("/resources/current")
async def get_current_resources() -> dict[str, Any]:
    """Get current resource usage."""
    from harness.core.resource_monitor import get_resource_monitor

    monitor = get_resource_monitor()
    return monitor.get_current()


@router.get("/resources/history")
async def get_resource_history(limit: int = 60) -> list[dict[str, Any]]:
    """Get resource usage history."""
    from harness.core.resource_monitor import get_resource_monitor

    monitor = get_resource_monitor()
    return monitor.get_recent_snapshots(limit)


@router.get("/resources/stats")
async def get_resource_stats() -> dict[str, Any]:
    """Get aggregated resource statistics."""
    from harness.core.resource_monitor import get_resource_monitor

    monitor = get_resource_monitor()
    return monitor.get_stats()


@router.post("/resources/reset")
async def reset_resource_monitoring() -> dict[str, str]:
    """Reset resource monitoring data."""
    from harness.core.resource_monitor import get_resource_monitor

    monitor = get_resource_monitor()
    monitor.reset()
    return {"status": "reset"}
