"""Metrics collection for observability and monitoring.

This module provides functions to collect and aggregate metrics about:
- Execution time
- Success rates
- Tool usage
- Component performance
- Resource usage
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from typing import Any


@dataclass
class MetricPoint:
    """A single metric data point."""

    timestamp: datetime
    value: float
    tags: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "value": self.value,
            "tags": self.tags,
        }


@dataclass
class CounterMetric:
    """A counter metric that can only increase."""

    name: str
    value: int = 0
    tags: dict[str, str] = field(default_factory=dict)

    def increment(self, amount: int = 1) -> None:
        """Increment the counter."""
        self.value += amount

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "tags": self.tags,
        }


@dataclass
class GaugeMetric:
    """A gauge metric that can go up or down."""

    name: str
    value: float = 0.0
    tags: dict[str, str] = field(default_factory=dict)

    def set(self, value: float) -> None:
        """Set the gauge value."""
        self.value = value

    def increment(self, amount: float = 1.0) -> None:
        """Increment the gauge."""
        self.value += amount

    def decrement(self, amount: float = 1.0) -> None:
        """Decrement the gauge."""
        self.value -= amount

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "tags": self.tags,
        }


@dataclass
class HistogramMetric:
    """A histogram metric for tracking distributions."""

    name: str
    values: list[float] = field(default_factory=list)
    tags: dict[str, str] = field(default_factory=dict)
    max_samples: int = 1000

    def observe(self, value: float) -> None:
        """Add a value to the histogram."""
        self.values.append(value)
        if len(self.values) > self.max_samples:
            self.values.pop(0)

    def summary(self) -> dict[str, float]:
        """Calculate summary statistics."""
        if not self.values:
            return {
                "count": 0,
                "min": 0.0,
                "max": 0.0,
                "mean": 0.0,
                "p50": 0.0,
                "p95": 0.0,
                "p99": 0.0,
            }

        sorted_values = sorted(self.values)
        n = len(sorted_values)

        return {
            "count": n,
            "min": sorted_values[0],
            "max": sorted_values[-1],
            "mean": sum(sorted_values) / n,
            "p50": sorted_values[int(n * 0.5)],
            "p95": sorted_values[int(n * 0.95)],
            "p99": sorted_values[int(n * 0.99)],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "summary": self.summary(),
            "tags": self.tags,
        }


class MetricsRegistry:
    """Central registry for all metrics."""

    def __init__(self) -> None:
        self._counters: dict[str, CounterMetric] = {}
        self._gauges: dict[str, GaugeMetric] = {}
        self._histograms: dict[str, HistogramMetric] = {}
        self._lock = Lock()

    def counter(self, name: str, tags: dict[str, str] | None = None) -> CounterMetric:
        """Get or create a counter metric."""
        key = self._make_key(name, tags)
        with self._lock:
            if key not in self._counters:
                self._counters[key] = CounterMetric(name=name, tags=tags or {})
            return self._counters[key]

    def gauge(self, name: str, tags: dict[str, str] | None = None) -> GaugeMetric:
        """Get or create a gauge metric."""
        key = self._make_key(name, tags)
        with self._lock:
            if key not in self._gauges:
                self._gauges[key] = GaugeMetric(name=name, tags=tags or {})
            return self._gauges[key]

    def histogram(self, name: str, tags: dict[str, str] | None = None) -> HistogramMetric:
        """Get or create a histogram metric."""
        key = self._make_key(name, tags)
        with self._lock:
            if key not in self._histograms:
                self._histograms[key] = HistogramMetric(name=name, tags=tags or {})
            return self._histograms[key]

    def _make_key(self, name: str, tags: dict[str, str] | None) -> str:
        """Create a unique key for a metric with tags."""
        if not tags:
            return name
        tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        return f"{name}{{{tag_str}}}"

    def get_all_metrics(self) -> dict[str, Any]:
        """Get all metrics as a dictionary."""
        with self._lock:
            return {
                "counters": [m.to_dict() for m in self._counters.values()],
                "gauges": [m.to_dict() for m in self._gauges.values()],
                "histograms": [m.to_dict() for m in self._histograms.values()],
            }

    def reset(self) -> None:
        """Reset all metrics."""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()


# Global metrics registry
_registry = MetricsRegistry()


def get_metrics_registry() -> MetricsRegistry:
    """Get the global metrics registry."""
    return _registry


# ── Metric helpers ───────────────────────────────────────────────────────────


def increment_counter(name: str, amount: int = 1, tags: dict[str, str] | None = None) -> None:
    """Increment a counter metric."""
    if tags is None:
        tags = {}
    _registry.counter(name, tags).increment(amount)


def set_gauge(name: str, value: float, tags: dict[str, str] | None = None) -> None:
    """Set a gauge metric."""
    _registry.gauge(name, tags).set(value)


def observe_histogram(name: str, value: float, tags: dict[str, str] | None = None) -> None:
    """Observe a value in a histogram."""
    _registry.histogram(name, tags).observe(value)


# ── Context manager for timing ─────────────────────────────────────────────────


class Timer:
    """Context manager for timing operations."""

    def __init__(self, metric_name: str, tags: dict[str, str] | None = None) -> None:
        self._metric_name = metric_name
        self._tags = tags
        self._start_time: float = 0.0

    def __enter__(self) -> Timer:
        self._start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        duration_ms = (time.time() - self._start_time) * 1000
        observe_histogram(self._metric_name, duration_ms, self._tags)

        # Also track success/failure
        if exc_type is None:
            increment_counter(f"{self._metric_name}_success", tags=self._tags)
        else:
            increment_counter(f"{self._metric_name}_error", tags=self._tags)


def time_operation(metric_name: str, tags: dict[str, str] | None = None) -> Timer:
    """Create a timer context manager."""
    return Timer(metric_name, tags)


# ── Predefined metrics ────────────────────────────────────────────────────────


def record_tool_execution(tool_name: str, duration_ms: float, success: bool, component_id: str | None = None) -> None:
    """Record a tool execution metric."""
    tags = {"tool": tool_name}
    if component_id:
        tags["component"] = component_id

    observe_histogram("tool_execution_duration_ms", duration_ms, tags)

    if success:
        increment_counter("tool_executions_success", tags=tags)
    else:
        increment_counter("tool_executions_error", tags=tags)

    # Check for alerts
    from harness.core.alerting import get_alert_manager
    alert_manager = get_alert_manager()
    counter = _registry.counter("tool_executions_error", tags)
    alert_manager.check_metric("tool_executions_error", counter.value)


def record_component_execution(component_id: str, duration_ms: float, success: bool) -> None:
    """Record a component execution metric."""
    tags = {"component": component_id}

    observe_histogram("component_execution_duration_ms", duration_ms, tags)

    if success:
        increment_counter("component_executions_success", tags)
    else:
        increment_counter("component_executions_error", tags)


def record_agent_run(run_id: str, duration_ms: float, steps_completed: int, steps_failed: int) -> None:
    """Record an agent run metric."""
    tags = {"run_id": run_id}

    observe_histogram("agent_run_duration_ms", duration_ms, tags)
    set_gauge("agent_run_steps_completed", steps_completed, tags)
    set_gauge("agent_run_steps_failed", steps_failed, tags)

    increment_counter("agent_runs_total")
