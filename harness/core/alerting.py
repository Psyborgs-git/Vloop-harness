"""Alerting system for detecting anomalies in metrics.

This module provides functionality to:
- Detect anomalies in metrics
- Configure alert thresholds
- Trigger alerts when thresholds are exceeded
- Track alert history
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from threading import Lock


class AlertSeverity(Enum):
    """Severity levels for alerts."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class Alert:
    """An alert triggered by an anomaly."""
    
    id: str
    metric_name: str
    severity: AlertSeverity
    message: str
    value: float
    threshold: float
    timestamp: datetime
    tags: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "metric_name": self.metric_name,
            "severity": self.severity.value,
            "message": self.message,
            "value": self.value,
            "threshold": self.threshold,
            "timestamp": self.timestamp.isoformat(),
            "tags": self.tags,
        }


@dataclass
class AlertRule:
    """A rule for triggering alerts."""
    
    metric_name: str
    threshold: float
    severity: AlertSeverity
    comparison: str = "greater_than"  # greater_than, less_than, equals
    window_seconds: int = 60
    min_samples: int = 1
    enabled: bool = True
    tags: Dict[str, str] = field(default_factory=dict)
    
    def should_alert(self, value: float) -> bool:
        """Check if the value should trigger an alert."""
        if not self.enabled:
            return False
        
        if self.comparison == "greater_than":
            return value > self.threshold
        elif self.comparison == "less_than":
            return value < self.threshold
        elif self.comparison == "equals":
            return value == self.threshold
        return False


class AlertManager:
    """Manages alert rules and alert history."""
    
    def __init__(self) -> None:
        self._rules: Dict[str, AlertRule] = {}
        self._alerts: deque[Alert] = deque(maxlen=1000)
        self._alert_handlers: List[Callable[[Alert], None]] = []
        self._lock = Lock()
    
    def add_rule(self, rule: AlertRule) -> None:
        """Add an alert rule."""
        with self._lock:
            self._rules[rule.metric_name] = rule
    
    def remove_rule(self, metric_name: str) -> None:
        """Remove an alert rule."""
        with self._lock:
            self._rules.pop(metric_name, None)
    
    def get_rule(self, metric_name: str) -> Optional[AlertRule]:
        """Get an alert rule by metric name."""
        with self._lock:
            return self._rules.get(metric_name)
    
    def list_rules(self) -> List[AlertRule]:
        """List all alert rules."""
        with self._lock:
            return list(self._rules.values())
    
    def check_metric(self, metric_name: str, value: float) -> Optional[Alert]:
        """Check if a metric value should trigger an alert."""
        rule = self.get_rule(metric_name)
        if not rule or not rule.enabled:
            return None
        
        if rule.should_alert(value):
            alert = Alert(
                id=str(int(time.time() * 1000)),
                metric_name=metric_name,
                severity=rule.severity,
                message=f"{metric_name} {rule.comparison} {rule.threshold}: {value}",
                value=value,
                threshold=rule.threshold,
                timestamp=datetime.now(timezone.utc),
                tags=rule.tags,
            )
            
            with self._lock:
                self._alerts.append(alert)
            
            # Notify handlers
            for handler in self._alert_handlers:
                try:
                    handler(alert)
                except Exception:
                    pass  # Don't let handler errors break the alerting
            
            return alert
        
        return None
    
    def add_handler(self, handler: Callable[[Alert], None]) -> None:
        """Add an alert handler callback."""
        with self._lock:
            self._alert_handlers.append(handler)
    
    def remove_handler(self, handler: Callable[[Alert], None]) -> None:
        """Remove an alert handler callback."""
        with self._lock:
            if handler in self._alert_handlers:
                self._alert_handlers.remove(handler)
    
    def get_recent_alerts(self, limit: int = 50) -> List[Alert]:
        """Get recent alerts."""
        with self._lock:
            alerts = list(self._alerts)
            return alerts[-limit:]
    
    def get_alerts_by_severity(self, severity: AlertSeverity, limit: int = 50) -> List[Alert]:
        """Get alerts by severity level."""
        with self._lock:
            alerts = [a for a in self._alerts if a.severity == severity]
            return alerts[-limit:]


# Global alert manager
_alert_manager = AlertManager()


def get_alert_manager() -> AlertManager:
    """Get the global alert manager."""
    return _alert_manager


# ── Default alert rules ───────────────────────────────────────────────────────


def setup_default_rules() -> None:
    """Set up default alert rules for common metrics."""
    manager = get_alert_manager()
    
    # High error rate
    manager.add_rule(AlertRule(
        metric_name="tool_executions_error",
        threshold=10,
        severity=AlertSeverity.WARNING,
        comparison="greater_than",
        tags={"category": "errors"},
    ))
    
    # Very high error rate
    manager.add_rule(AlertRule(
        metric_name="tool_executions_error",
        threshold=50,
        severity=AlertSeverity.CRITICAL,
        comparison="greater_than",
        tags={"category": "errors"},
    ))
    
    # Slow tool execution
    manager.add_rule(AlertRule(
        metric_name="tool_execution_duration_ms_p95",
        threshold=5000,
        severity=AlertSeverity.WARNING,
        comparison="greater_than",
        tags={"category": "performance"},
    ))
    
    # Very slow tool execution
    manager.add_rule(AlertRule(
        metric_name="tool_execution_duration_ms_p95",
        threshold=10000,
        severity=AlertSeverity.ERROR,
        comparison="greater_than",
        tags={"category": "performance"},
    ))
    
    # Slow component execution
    manager.add_rule(AlertRule(
        metric_name="component_execution_duration_ms_p95",
        threshold=10000,
        severity=AlertSeverity.WARNING,
        comparison="greater_than",
        tags={"category": "performance"},
    ))


# ── Alert handlers ───────────────────────────────────────────────────────────


def log_alert_handler(alert: Alert) -> None:
    """Log alerts to the logger."""
    from harness.core.logger import HarnessLogger
    
    logger = HarnessLogger()
    level = {
        AlertSeverity.INFO: "info",
        AlertSeverity.WARNING: "warn",
        AlertSeverity.ERROR: "error",
        AlertSeverity.CRITICAL: "error",
    }[alert.severity]
    
    getattr(logger, level)(
        f"Alert: {alert.message}",
        metric_name=alert.metric_name,
        value=alert.value,
        threshold=alert.threshold,
        severity=alert.severity.value,
    )


def setup_default_handlers() -> None:
    """Set up default alert handlers."""
    manager = get_alert_manager()
    manager.add_handler(log_alert_handler)
