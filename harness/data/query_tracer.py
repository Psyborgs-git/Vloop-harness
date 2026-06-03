"""Query performance tracking for database operations.

This module provides functionality to:
- Track query execution time
- Record query patterns
- Identify slow queries
- Aggregate query statistics
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List
from threading import Lock


@dataclass
class QueryTrace:
    """A single query execution trace."""

    query: str
    duration_ms: float
    timestamp: datetime
    success: bool
    error: str | None = None
    params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query[:1000],  # Truncate long queries
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp.isoformat(),
            "success": self.success,
            "error": self.error,
            "params": self.params,
        }


@dataclass
class QueryStats:
    """Statistics for a query pattern."""

    pattern: str = ""
    count: int = 0
    total_duration_ms: float = 0.0
    min_duration_ms: float = float("inf")
    max_duration_ms: float = 0.0
    error_count: int = 0

    @property
    def avg_duration_ms(self) -> float:
        if self.count == 0:
            return 0.0
        return self.total_duration_ms / self.count

    def add_trace(self, trace: QueryTrace) -> None:
        """Add a trace to the statistics."""
        self.count += 1
        self.total_duration_ms += trace.duration_ms
        self.min_duration_ms = min(self.min_duration_ms, trace.duration_ms)
        self.max_duration_ms = max(self.max_duration_ms, trace.duration_ms)
        if not trace.success:
            self.error_count += 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern": self.pattern,
            "count": self.count,
            "avg_duration_ms": self.avg_duration_ms,
            "min_duration_ms": self.min_duration_ms if self.min_duration_ms != float("inf") else 0,
            "max_duration_ms": self.max_duration_ms,
            "error_count": self.error_count,
            "error_rate": self.error_count / self.count if self.count > 0 else 0,
        }


class QueryTracer:
    """Tracks database query performance."""

    def __init__(self, slow_query_threshold_ms: float = 1000.0, max_traces: int = 1000) -> None:
        self._slow_query_threshold_ms = slow_query_threshold_ms
        self._traces: List[QueryTrace] = []
        self._stats: Dict[str, QueryStats] = {}
        self._lock = Lock()
        self._max_traces = max_traces

    def trace_query(
        self,
        query: str,
        duration_ms: float,
        success: bool = True,
        error: str | None = None,
        params: Dict[str, Any] | None = None,
    ) -> None:
        """Record a query execution."""
        trace = QueryTrace(
            query=query,
            duration_ms=duration_ms,
            timestamp=datetime.now(timezone.utc),
            success=success,
            error=error,
            params=params or {},
        )

        with self._lock:
            self._traces.append(trace)
            if len(self._traces) > self._max_traces:
                self._traces.pop(0)

            # Update statistics
            pattern = self._normalize_query(query)
            if pattern not in self._stats:
                self._stats[pattern] = QueryStats(pattern=pattern)
            self._stats[pattern].add_trace(trace)

    def _normalize_query(self, query: str) -> str:
        """Normalize a query for pattern matching."""
        # Remove parameter values and normalize whitespace
        import re
        normalized = re.sub(r"'[^']*'", "'?'", query)  # Replace string literals
        normalized = re.sub(r'\b\d+\b', '?', normalized)  # Replace numbers
        normalized = re.sub(r'\s+', ' ', normalized).strip()  # Normalize whitespace
        return normalized[:200]  # Truncate

    def get_recent_traces(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent query traces."""
        with self._lock:
            traces = self._traces[-limit:]
            return [t.to_dict() for t in traces]

    def get_slow_queries(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get slow queries (above threshold)."""
        with self._lock:
            slow = [t for t in self._traces if t.duration_ms > self._slow_query_threshold_ms]
            slow_sorted = sorted(slow, key=lambda t: t.duration_ms, reverse=True)
            return [t.to_dict() for t in slow_sorted[:limit]]

    def get_query_stats(self) -> List[Dict[str, Any]]:
        """Get aggregated query statistics."""
        with self._lock:
            return [stats.to_dict() for stats in self._stats.values()]

    def get_stats_by_pattern(self, pattern: str) -> Dict[str, Any] | None:
        """Get statistics for a specific query pattern."""
        with self._lock:
            stats = self._stats.get(pattern)
            return stats.to_dict() if stats else None

    def reset(self) -> None:
        """Reset all traces and statistics."""
        with self._lock:
            self._traces.clear()
            self._stats.clear()


# Global query tracer
_query_tracer = QueryTracer()


def get_query_tracer() -> QueryTracer:
    """Get the global query tracer."""
    return _query_tracer


# ── Context manager for query tracing ─────────────────────────────────────────


class QueryTimer:
    """Context manager for timing queries."""

    def __init__(self, query: str, params: Dict[str, Any] | None = None) -> None:
        self._query = query
        self._params = params
        self._start_time: float = 0.0
        self._success = True
        self._error: str | None = None

    def __enter__(self) -> "QueryTimer":
        self._start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        duration_ms = (time.time() - self._start_time) * 1000

        if exc_type is not None:
            self._success = False
            self._error = str(exc_val)

        get_query_tracer().trace_query(
            query=self._query,
            duration_ms=duration_ms,
            success=self._success,
            error=self._error,
            params=self._params,
        )


def trace_query(query: str, params: Dict[str, Any] | None = None) -> QueryTimer:
    """Create a query timer context manager."""
    return QueryTimer(query, params)
