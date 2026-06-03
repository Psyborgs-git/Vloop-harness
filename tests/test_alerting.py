"""Tests for alerting system."""

import pytest

from harness.core.alerting import (
    Alert,
    AlertManager,
    AlertRule,
    AlertSeverity,
    get_alert_manager,
    setup_default_handlers,
    setup_default_rules,
)


def test_alert_creation():
    """Test Alert creation and serialization."""
    from datetime import datetime, timezone

    alert = Alert(
        id="test_123",
        metric_name="test_metric",
        severity=AlertSeverity.WARNING,
        message="Test alert",
        value=100.0,
        threshold=50.0,
        timestamp=datetime.now(timezone.utc),
    )

    assert alert.metric_name == "test_metric"
    assert alert.severity == AlertSeverity.WARNING

    data = alert.to_dict()
    assert data["metric_name"] == "test_metric"
    assert data["severity"] == "warning"


def test_alert_rule_creation():
    """Test AlertRule creation."""
    rule = AlertRule(
        metric_name="test_metric",
        threshold=50.0,
        severity=AlertSeverity.ERROR,
        comparison="greater_than",
    )

    assert rule.metric_name == "test_metric"
    assert rule.threshold == 50.0
    assert rule.enabled is True


def test_alert_rule_should_alert():
    """Test AlertRule.should_alert logic."""
    rule = AlertRule(
        metric_name="test_metric",
        threshold=50.0,
        severity=AlertSeverity.ERROR,
        comparison="greater_than",
    )

    assert rule.should_alert(60.0) is True
    assert rule.should_alert(40.0) is False


def test_alert_rule_less_than():
    """Test AlertRule with less_than comparison."""
    rule = AlertRule(
        metric_name="test_metric",
        threshold=10.0,
        severity=AlertSeverity.WARNING,
        comparison="less_than",
    )

    assert rule.should_alert(5.0) is True
    assert rule.should_alert(15.0) is False


def test_alert_rule_disabled():
    """Test AlertRule when disabled."""
    rule = AlertRule(
        metric_name="test_metric",
        threshold=50.0,
        severity=AlertSeverity.ERROR,
        comparison="greater_than",
        enabled=False,
    )

    assert rule.should_alert(100.0) is False


def test_alert_manager_add_rule():
    """Test AlertManager.add_rule."""
    manager = AlertManager()
    rule = AlertRule(
        metric_name="test_metric",
        threshold=50.0,
        severity=AlertSeverity.ERROR,
    )

    manager.add_rule(rule)

    retrieved = manager.get_rule("test_metric")
    assert retrieved is not None
    assert retrieved.metric_name == "test_metric"


def test_alert_manager_remove_rule():
    """Test AlertManager.remove_rule."""
    manager = AlertManager()
    rule = AlertRule(
        metric_name="test_metric",
        threshold=50.0,
        severity=AlertSeverity.ERROR,
    )

    manager.add_rule(rule)
    manager.remove_rule("test_metric")

    retrieved = manager.get_rule("test_metric")
    assert retrieved is None


def test_alert_manager_check_metric():
    """Test AlertManager.check_metric."""
    manager = AlertManager()
    rule = AlertRule(
        metric_name="test_metric",
        threshold=50.0,
        severity=AlertSeverity.ERROR,
    )

    manager.add_rule(rule)
    alert = manager.check_metric("test_metric", 60.0)

    assert alert is not None
    assert alert.metric_name == "test_metric"
    assert alert.value == 60.0


def test_alert_manager_no_alert():
    """Test AlertManager.check_metric when no alert should trigger."""
    manager = AlertManager()
    rule = AlertRule(
        metric_name="test_metric",
        threshold=50.0,
        severity=AlertSeverity.ERROR,
    )

    manager.add_rule(rule)
    alert = manager.check_metric("test_metric", 40.0)

    assert alert is None


def test_alert_manager_get_recent_alerts():
    """Test AlertManager.get_recent_alerts."""
    manager = AlertManager()
    rule = AlertRule(
        metric_name="test_metric",
        threshold=50.0,
        severity=AlertSeverity.ERROR,
    )

    manager.add_rule(rule)
    manager.check_metric("test_metric", 60.0)
    manager.check_metric("test_metric", 70.0)

    alerts = manager.get_recent_alerts(limit=10)
    assert len(alerts) == 2


def test_alert_manager_handler():
    """Test AlertManager with custom handler."""
    manager = AlertManager()
    rule = AlertRule(
        metric_name="test_metric",
        threshold=50.0,
        severity=AlertSeverity.ERROR,
    )

    handler_called = []

    def handler(alert):
        handler_called.append(alert)

    manager.add_handler(handler)
    manager.add_rule(rule)
    manager.check_metric("test_metric", 60.0)

    assert len(handler_called) == 1
    assert handler_called[0].metric_name == "test_metric"


def test_setup_default_rules():
    """Test setup_default_rules."""
    setup_default_rules()

    manager = get_alert_manager()
    rules = manager.list_rules()

    assert len(rules) > 0

    # Check for expected rules
    rule_names = [r.metric_name for r in rules]
    assert "tool_executions_error" in rule_names


def test_setup_default_handlers():
    """Test setup_default_handlers."""
    setup_default_handlers()

    manager = get_alert_manager()
    # Should have at least the log handler
    assert len(manager._alert_handlers) > 0
