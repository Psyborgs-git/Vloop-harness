"""Resource usage monitoring for system health.

This module provides functionality to:
- Monitor CPU usage
- Monitor memory usage
- Monitor disk usage
- Track resource trends
- Alert on resource exhaustion
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Any

import psutil


@dataclass
class ResourceSnapshot:
    """A snapshot of system resource usage."""
    
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_available_mb: float
    disk_percent: float
    disk_used_gb: float
    disk_free_gb: float
    process_count: int
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
            "memory_used_mb": self.memory_used_mb,
            "memory_available_mb": self.memory_available_mb,
            "disk_percent": self.disk_percent,
            "disk_used_gb": self.disk_used_gb,
            "disk_free_gb": self.disk_free_gb,
            "process_count": self.process_count,
        }


@dataclass
class ResourceStats:
    """Statistics for resource usage over time."""
    
    cpu_avg: float = 0.0
    cpu_max: float = 0.0
    memory_avg: float = 0.0
    memory_max: float = 0.0
    disk_avg: float = 0.0
    disk_max: float = 0.0
    
    def add_snapshot(self, snapshot: ResourceSnapshot) -> None:
        """Update statistics with a new snapshot."""
        self.cpu_max = max(self.cpu_max, snapshot.cpu_percent)
        self.memory_max = max(self.memory_max, snapshot.memory_percent)
        self.disk_max = max(self.disk_max, snapshot.disk_percent)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "cpu_avg": self.cpu_avg,
            "cpu_max": self.cpu_max,
            "memory_avg": self.memory_avg,
            "memory_max": self.memory_max,
            "disk_avg": self.disk_avg,
            "disk_max": self.disk_max,
        }


class ResourceMonitor:
    """Monitors system resource usage."""
    
    def __init__(self, max_snapshots: int = 3600) -> None:
        self._max_snapshots = max_snapshots
        self._snapshots: deque[ResourceSnapshot] = deque(maxlen=max_snapshots)
        self._stats = ResourceStats()
        self._lock = Lock()
        self._running = False
        self._interval_seconds = 5
    
    def take_snapshot(self) -> ResourceSnapshot:
        """Take a snapshot of current resource usage."""
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            process_count = len(psutil.pids())
            
            snapshot = ResourceSnapshot(
                timestamp=datetime.now(UTC),
                cpu_percent=cpu_percent,
                memory_percent=memory.percent,
                memory_used_mb=memory.used / (1024 * 1024),
                memory_available_mb=memory.available / (1024 * 1024),
                disk_percent=disk.percent,
                disk_used_gb=disk.used / (1024 * 1024 * 1024),
                disk_free_gb=disk.free / (1024 * 1024 * 1024),
                process_count=process_count,
            )
            
            with self._lock:
                self._snapshots.append(snapshot)
                self._stats.add_snapshot(snapshot)
            
            return snapshot
        except Exception:
            # Return a default snapshot if psutil fails
            return ResourceSnapshot(
                timestamp=datetime.now(UTC),
                cpu_percent=0.0,
                memory_percent=0.0,
                memory_used_mb=0.0,
                memory_available_mb=0.0,
                disk_percent=0.0,
                disk_used_gb=0.0,
                disk_free_gb=0.0,
                process_count=0,
            )
    
    def get_current(self) -> dict[str, Any]:
        """Get current resource usage."""
        snapshot = self.take_snapshot()
        return snapshot.to_dict()
    
    def get_recent_snapshots(self, limit: int = 60) -> list[dict[str, Any]]:
        """Get recent resource snapshots."""
        with self._lock:
            snapshots = list(self._snapshots)[-limit:]
            return [s.to_dict() for s in snapshots]
    
    def get_stats(self) -> dict[str, Any]:
        """Get aggregated resource statistics."""
        with self._lock:
            if not self._snapshots:
                return self._stats.to_dict()
            
            # Calculate averages
            snapshots = list(self._snapshots)
            self._stats.cpu_avg = sum(s.cpu_percent for s in snapshots) / len(snapshots)
            self._stats.memory_avg = sum(s.memory_percent for s in snapshots) / len(snapshots)
            self._stats.disk_avg = sum(s.disk_percent for s in snapshots) / len(snapshots)
            
            return self._stats.to_dict()
    
    def reset(self) -> None:
        """Reset all snapshots and statistics."""
        with self._lock:
            self._snapshots.clear()
            self._stats = ResourceStats()
    
    def start_monitoring(self, interval_seconds: int = 5) -> None:
        """Start continuous monitoring in a background thread."""
        import threading
        
        self._interval_seconds = interval_seconds
        self._running = True
        
        def monitor_loop():
            while self._running:
                self.take_snapshot()
                time.sleep(self._interval_seconds)
        
        thread = threading.Thread(target=monitor_loop, daemon=True)
        thread.start()
    
    def stop_monitoring(self) -> None:
        """Stop continuous monitoring."""
        self._running = False


# Global resource monitor
_resource_monitor = ResourceMonitor()


def get_resource_monitor() -> ResourceMonitor:
    """Get the global resource monitor."""
    return _resource_monitor


# ── Resource metrics integration ─────────────────────────────────────────────


def record_resource_metrics() -> None:
    """Record current resource usage as metrics."""
    from harness.core.metrics import observe_histogram, set_gauge
    
    snapshot = get_resource_monitor().take_snapshot()
    
    set_gauge("resource_cpu_percent", snapshot.cpu_percent)
    set_gauge("resource_memory_percent", snapshot.memory_percent)
    set_gauge("resource_disk_percent", snapshot.disk_percent)
    set_gauge("resource_process_count", snapshot.process_count)
    
    observe_histogram("resource_memory_used_mb", snapshot.memory_used_mb)
    observe_histogram("resource_disk_used_gb", snapshot.disk_used_gb)
