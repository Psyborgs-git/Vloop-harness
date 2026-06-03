"""Tests for metrics system."""

import pytest

from harness.core.metrics import (
    CounterMetric,
    GaugeMetric,
    HistogramMetric,
    MetricsRegistry,
    Timer,
    get_metrics_registry,
    increment_counter,
    observe_histogram,
    record_tool_execution,
    set_gauge,
    time_operation,
)


def test_counter_metric():
    """Test CounterMetric functionality."""
    counter = CounterMetric(name="test_counter")
    
    assert counter.value == 0
    counter.increment()
    assert counter.value == 1
    counter.increment(5)
    assert counter.value == 6
    
    data = counter.to_dict()
    assert data["name"] == "test_counter"
    assert data["value"] == 6


def test_gauge_metric():
    """Test GaugeMetric functionality."""
    gauge = GaugeMetric(name="test_gauge")
    
    gauge.set(10.5)
    assert gauge.value == 10.5
    
    gauge.increment(2.5)
    assert gauge.value == 13.0
    
    gauge.decrement(3.0)
    assert gauge.value == 10.0


def test_histogram_metric():
    """Test HistogramMetric functionality."""
    hist = HistogramMetric(name="test_histogram")
    
    hist.observe(10.0)
    hist.observe(20.0)
    hist.observe(30.0)
    
    assert len(hist.values) == 3
    
    summary = hist.summary()
    assert summary["count"] == 3
    assert summary["min"] == 10.0
    assert summary["max"] == 30.0
    assert summary["mean"] == 20.0


def test_metrics_registry():
    """Test MetricsRegistry functionality."""
    registry = MetricsRegistry()
    
    counter = registry.counter("test_counter")
    counter.increment()
    
    gauge = registry.gauge("test_gauge")
    gauge.set(5.0)
    
    hist = registry.histogram("test_histogram")
    hist.observe(10.0)
    
    all_metrics = registry.get_all_metrics()
    assert len(all_metrics["counters"]) == 1
    assert len(all_metrics["gauges"]) == 1
    assert len(all_metrics["histograms"]) == 1


def test_metrics_registry_tags():
    """Test MetricsRegistry with tags."""
    registry = MetricsRegistry()
    
    counter1 = registry.counter("test_counter", {"tool": "terminal"})
    counter1.increment()
    
    counter2 = registry.counter("test_counter", {"tool": "browser"})
    counter2.increment()
    
    all_metrics = registry.get_all_metrics()
    assert len(all_metrics["counters"]) == 2


def test_metrics_registry_reset():
    """Test MetricsRegistry reset."""
    registry = MetricsRegistry()
    
    counter = registry.counter("test_counter")
    counter.increment()
    
    registry.reset()
    
    all_metrics = registry.get_all_metrics()
    assert len(all_metrics["counters"]) == 0


def test_increment_counter():
    """Test increment_counter helper."""
    increment_counter("test_counter", 5)
    
    registry = get_metrics_registry()
    all_metrics = registry.get_all_metrics()
    
    counters = all_metrics["counters"]
    assert len(counters) == 1
    assert counters[0]["value"] == 5


def test_set_gauge():
    """Test set_gauge helper."""
    set_gauge("test_gauge", 42.0)
    
    registry = get_metrics_registry()
    all_metrics = registry.get_all_metrics()
    
    gauges = all_metrics["gauges"]
    assert len(gauges) == 1
    assert gauges[0]["value"] == 42.0


def test_observe_histogram():
    """Test observe_histogram helper."""
    observe_histogram("test_histogram", 15.0)
    
    registry = get_metrics_registry()
    all_metrics = registry.get_all_metrics()
    
    histograms = all_metrics["histograms"]
    assert len(histograms) == 1
    assert histograms[0]["summary"]["count"] == 1


def test_timer_context_manager():
    """Test Timer context manager."""
    import time
    
    with Timer("test_operation") as timer:
        time.sleep(0.01)
    
    registry = get_metrics_registry()
    all_metrics = registry.get_all_metrics()
    
    histograms = all_metrics["histograms"]
    assert len(histograms) > 0
    
    # Check for success counter
    counters = all_metrics["counters"]
    success_counters = [c for c in counters if "test_operation_success" in c["name"]]
    assert len(success_counters) > 0


def test_timer_error():
    """Test Timer with error."""
    with pytest.raises(ValueError):
        with Timer("test_operation"):
            raise ValueError("test error")
    
    registry = get_metrics_registry()
    all_metrics = registry.get_all_metrics()
    
    # Check for error counter
    counters = all_metrics["counters"]
    error_counters = [c for c in counters if "test_operation_error" in c["name"]]
    assert len(error_counters) > 0


def test_record_tool_execution():
    """Test record_tool_execution helper."""
    record_tool_execution("terminal", 100.0, True, "component_123")
    
    registry = get_metrics_registry()
    all_metrics = registry.get_all_metrics()
    
    # Check for histogram
    histograms = all_metrics["histograms"]
    tool_hist = [h for h in histograms if "tool_execution_duration_ms" in h["name"]]
    assert len(tool_hist) > 0
    
    # Check for success counter
    counters = all_metrics["counters"]
    success_counter = [c for c in counters if "tool_executions_success" in c["name"]]
    assert len(success_counter) > 0


def test_record_tool_execution_failure():
    """Test record_tool_execution with failure."""
    record_tool_execution("terminal", 100.0, False, "component_123")
    
    registry = get_metrics_registry()
    all_metrics = registry.get_all_metrics()
    
    # Check for error counter
    counters = all_metrics["counters"]
    error_counter = [c for c in counters if "tool_executions_error" in c["name"]]
    assert len(error_counter) > 0
