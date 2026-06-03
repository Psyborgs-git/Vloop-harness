"""Tests for resource monitor."""

import pytest

from harness.core.resource_monitor import (
    ResourceMonitor,
    ResourceSnapshot,
    ResourceStats,
    get_resource_monitor,
    record_resource_metrics,
)


def test_resource_snapshot():
    """Test ResourceSnapshot creation and serialization."""
    from datetime import datetime, timezone

    snapshot = ResourceSnapshot(
        cpu_percent=50.0,
        memory_percent=60.0,
        memory_used_mb=1024.0,
        memory_available_mb=2048.0,
        disk_percent=70.0,
        disk_used_gb=100.0,
        disk_free_gb=50.0,
        process_count=100,
        timestamp=datetime.now(timezone.utc),
    )

    assert snapshot.cpu_percent == 50.0
    assert snapshot.memory_percent == 60.0

    data = snapshot.to_dict()
    assert data["cpu_percent"] == 50.0
    assert data["memory_percent"] == 60.0


def test_resource_stats():
    """Test ResourceStats functionality."""
    from datetime import datetime, timezone

    stats = ResourceStats()

    snapshot1 = ResourceSnapshot(
        cpu_percent=30.0,
        memory_percent=40.0,
        memory_used_mb=512.0,
        memory_available_mb=1024.0,
        disk_percent=50.0,
        disk_used_gb=50.0,
        disk_free_gb=50.0,
        process_count=50,
        timestamp=datetime.now(timezone.utc),
    )

    snapshot2 = ResourceSnapshot(
        cpu_percent=60.0,
        memory_percent=70.0,
        memory_used_mb=1024.0,
        memory_available_mb=512.0,
        disk_percent=80.0,
        disk_used_gb=80.0,
        disk_free_gb=20.0,
        process_count=100,
        timestamp=datetime.now(timezone.utc),
    )

    stats.add_snapshot(snapshot1)
    stats.add_snapshot(snapshot2)

    assert stats.cpu_max == 60.0
    assert stats.memory_max == 70.0
    assert stats.disk_max == 80.0


def test_resource_monitor_take_snapshot():
    """Test ResourceMonitor.take_snapshot."""
    monitor = ResourceMonitor()

    snapshot = monitor.take_snapshot()

    assert isinstance(snapshot, ResourceSnapshot)
    assert snapshot.cpu_percent >= 0
    assert snapshot.memory_percent >= 0
    assert snapshot.disk_percent >= 0


def test_resource_monitor_get_current():
    """Test ResourceMonitor.get_current."""
    monitor = ResourceMonitor()

    current = monitor.get_current()

    assert "cpu_percent" in current
    assert "memory_percent" in current
    assert "disk_percent" in current
    assert "process_count" in current


def test_resource_monitor_get_recent_snapshots():
    """Test ResourceMonitor.get_recent_snapshots."""
    monitor = ResourceMonitor()

    monitor.take_snapshot()
    monitor.take_snapshot()
    monitor.take_snapshot()

    snapshots = monitor.get_recent_snapshots(limit=2)
    assert len(snapshots) == 2


def test_resource_monitor_get_stats():
    """Test ResourceMonitor.get_stats."""
    monitor = ResourceMonitor()

    monitor.take_snapshot()
    monitor.take_snapshot()

    stats = monitor.get_stats()

    assert "cpu_avg" in stats
    assert "cpu_max" in stats
    assert "memory_avg" in stats


def test_resource_monitor_reset():
    """Test ResourceMonitor.reset."""
    monitor = ResourceMonitor()

    monitor.take_snapshot()
    monitor.reset()

    snapshots = monitor.get_recent_snapshots()
    stats = monitor.get_stats()

    assert len(snapshots) == 0
    assert stats["cpu_max"] == 0


def test_resource_monitor_max_snapshots():
    """Test ResourceMonitor max snapshots limit."""
    monitor = ResourceMonitor(max_snapshots=5)

    for _ in range(10):
        monitor.take_snapshot()

    snapshots = monitor.get_recent_snapshots()
    assert len(snapshots) == 5


def test_get_resource_monitor():
    """Test get_resource_monitor singleton."""
    monitor1 = get_resource_monitor()
    monitor2 = get_resource_monitor()

    assert monitor1 is monitor2


def test_record_resource_metrics():
    """Test record_resource_metrics helper."""
    from harness.core.metrics import get_metrics_registry

    # Clear existing metrics
    registry = get_metrics_registry()
    registry.reset()

    record_resource_metrics()

    all_metrics = registry.get_all_metrics()

    # Check for resource metrics
    gauges = all_metrics["gauges"]
    resource_gauges = [g for g in gauges if "resource_" in g["name"]]
    assert len(resource_gauges) > 0

    histograms = all_metrics["histograms"]
    resource_histograms = [h for h in histograms if "resource_" in h["name"]]
    assert len(resource_histograms) > 0
