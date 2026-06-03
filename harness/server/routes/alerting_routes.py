"""REST routes for alerting and anomaly detection.

Endpoints
─────────
  GET /api/alerts/rules — List alert rules
  POST /api/alerts/rules — Create alert rule
  PUT /api/alerts/rules/{metric_name} — Update alert rule
  DELETE /api/alerts/rules/{metric_name} — Delete alert rule
  GET /api/alerts — List recent alerts
  GET /api/alerts/{severity} — List alerts by severity
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from harness.core.alerting import AlertManager, AlertRule, AlertSeverity, get_alert_manager

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


# ── Request / Response models ─────────────────────────────────────────────────


class AlertRuleCreateRequest(BaseModel):
    metric_name: str
    threshold: float
    severity: str  # info, warning, error, critical
    comparison: str = "greater_than"
    window_seconds: int = 60
    min_samples: int = 1
    enabled: bool = True
    tags: dict[str, str] = {}


class AlertRuleUpdateRequest(BaseModel):
    threshold: float | None = None
    severity: str | None = None
    comparison: str | None = None
    window_seconds: int | None = None
    min_samples: int | None = None
    enabled: bool | None = None
    tags: dict[str, str] | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────


def _severity_from_string(s: str) -> AlertSeverity:
    try:
        return AlertSeverity(s.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid severity: {s}")


def _rule_to_dict(rule: AlertRule) -> dict[str, Any]:
    return {
        "metric_name": rule.metric_name,
        "threshold": rule.threshold,
        "severity": rule.severity.value,
        "comparison": rule.comparison,
        "window_seconds": rule.window_seconds,
        "min_samples": rule.min_samples,
        "enabled": rule.enabled,
        "tags": rule.tags,
    }


def _alert_to_dict(alert) -> dict[str, Any]:
    return alert.to_dict()


# ── Alert rules endpoints ─────────────────────────────────────────────────────


@router.get("/rules")
async def list_alert_rules() -> list[dict[str, Any]]:
    """List all alert rules."""
    manager = get_alert_manager()
    return [_rule_to_dict(rule) for rule in manager.list_rules()]


@router.post("/rules", status_code=201)
async def create_alert_rule(body: AlertRuleCreateRequest) -> dict[str, Any]:
    """Create a new alert rule."""
    manager = get_alert_manager()
    
    rule = AlertRule(
        metric_name=body.metric_name,
        threshold=body.threshold,
        severity=_severity_from_string(body.severity),
        comparison=body.comparison,
        window_seconds=body.window_seconds,
        min_samples=body.min_samples,
        enabled=body.enabled,
        tags=body.tags,
    )
    
    manager.add_rule(rule)
    return _rule_to_dict(rule)


@router.put("/rules/{metric_name}")
async def update_alert_rule(
    metric_name: str,
    body: AlertRuleUpdateRequest,
) -> dict[str, Any]:
    """Update an alert rule."""
    manager = get_alert_manager()
    rule = manager.get_rule(metric_name)
    
    if not rule:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    
    if body.threshold is not None:
        rule.threshold = body.threshold
    if body.severity is not None:
        rule.severity = _severity_from_string(body.severity)
    if body.comparison is not None:
        rule.comparison = body.comparison
    if body.window_seconds is not None:
        rule.window_seconds = body.window_seconds
    if body.min_samples is not None:
        rule.min_samples = body.min_samples
    if body.enabled is not None:
        rule.enabled = body.enabled
    if body.tags is not None:
        rule.tags = body.tags
    
    return _rule_to_dict(rule)


@router.delete("/rules/{metric_name}", status_code=204)
async def delete_alert_rule(metric_name: str) -> None:
    """Delete an alert rule."""
    manager = get_alert_manager()
    manager.remove_rule(metric_name)


# ── Alerts endpoints ─────────────────────────────────────────────────────────


@router.get("")
async def list_alerts(limit: int = 50) -> list[dict[str, Any]]:
    """List recent alerts."""
    manager = get_alert_manager()
    return [_alert_to_dict(alert) for alert in manager.get_recent_alerts(limit)]


@router.get("/{severity}")
async def list_alerts_by_severity(severity: str, limit: int = 50) -> list[dict[str, Any]]:
    """List alerts by severity level."""
    manager = get_alert_manager()
    alert_severity = _severity_from_string(severity)
    return [_alert_to_dict(alert) for alert in manager.get_alerts_by_severity(alert_severity, limit)]
