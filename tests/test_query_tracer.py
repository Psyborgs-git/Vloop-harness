"""Tests for query tracer."""

import pytest

from harness.data.query_tracer import (
    QueryStats,
    QueryTimer,
    QueryTrace,
    QueryTracer,
    get_query_tracer,
    trace_query,
)


def test_query_trace():
    """Test QueryTrace creation and serialization."""
    from datetime import datetime, timezone

    trace = QueryTrace(
        query="SELECT * FROM users",
        duration_ms=10.5,
        success=True,
        params={"limit": 10},
        timestamp=datetime.now(timezone.utc),
    )

    assert trace.query == "SELECT * FROM users"
    assert trace.duration_ms == 10.5
    assert trace.success is True

    data = trace.to_dict()
    assert data["query"] == "SELECT * FROM users"
    assert data["duration_ms"] == 10.5


def test_query_stats():
    """Test QueryStats functionality."""
    from datetime import datetime, timezone

    stats = QueryStats(pattern="SELECT * FROM users")

    trace1 = QueryTrace(query="SELECT * FROM users", duration_ms=10.0, success=True, timestamp=datetime.now(timezone.utc))
    trace2 = QueryTrace(query="SELECT * FROM users", duration_ms=20.0, success=True, timestamp=datetime.now(timezone.utc))
    trace3 = QueryTrace(query="SELECT * FROM users", duration_ms=15.0, success=False, timestamp=datetime.now(timezone.utc))

    stats.add_trace(trace1)
    stats.add_trace(trace2)
    stats.add_trace(trace3)

    assert stats.count == 3
    assert stats.avg_duration_ms == 15.0
    assert stats.min_duration_ms == 10.0
    assert stats.max_duration_ms == 20.0
    assert stats.error_count == 1

    data = stats.to_dict()
    assert data["count"] == 3
    assert data["avg_duration_ms"] == 15.0


def test_query_tracer_trace():
    """Test QueryTracer.trace_query."""
    tracer = QueryTracer()

    tracer.trace_query(
        query="SELECT * FROM users",
        duration_ms=10.5,
        success=True,
        params={"limit": 10},
    )

    traces = tracer.get_recent_traces(limit=10)
    assert len(traces) == 1
    assert traces[0]["query"] == "SELECT * FROM users"


def test_query_tracer_normalize():
    """Test QueryTracer._normalize_query."""
    tracer = QueryTracer()

    query1 = "SELECT * FROM users WHERE id = 123"
    query2 = "SELECT * FROM users WHERE id = 456"

    normalized1 = tracer._normalize_query(query1)
    normalized2 = tracer._normalize_query(query2)

    assert normalized1 == normalized2
    assert "?" in normalized1


def test_query_tracer_slow_queries():
    """Test QueryTracer.get_slow_queries."""
    tracer = QueryTracer(slow_query_threshold_ms=50.0)

    tracer.trace_query("SELECT 1", 10.0, True)
    tracer.trace_query("SELECT 2", 100.0, True)
    tracer.trace_query("SELECT 3", 200.0, True)

    slow = tracer.get_slow_queries(limit=10)
    assert len(slow) == 2
    assert all(q["duration_ms"] > 50.0 for q in slow)


def test_query_tracer_stats():
    """Test QueryTracer.get_query_stats."""
    tracer = QueryTracer()

    tracer.trace_query("SELECT * FROM users", 10.0, True)
    tracer.trace_query("SELECT * FROM users", 20.0, True)
    tracer.trace_query("SELECT * FROM posts", 15.0, True)

    stats = tracer.get_query_stats()
    assert len(stats) == 2

    # Find the users stats
    users_stats = [s for s in stats if "users" in s["pattern"]]
    assert len(users_stats) == 1
    assert users_stats[0]["count"] == 2


def test_query_tracer_reset():
    """Test QueryTracer.reset."""
    tracer = QueryTracer()

    tracer.trace_query("SELECT 1", 10.0, True)
    tracer.reset()

    traces = tracer.get_recent_traces()
    stats = tracer.get_query_stats()

    assert len(traces) == 0
    assert len(stats) == 0


def test_query_timer_context_manager():
    """Test QueryTimer context manager."""
    import time

    from harness.data.query_tracer import get_query_tracer

    tracer = get_query_tracer()
    query = "SELECT * FROM users"

    with QueryTimer(query):
        time.sleep(0.01)

    traces = tracer.get_recent_traces()
    assert len(traces) >= 1
    assert traces[-1]["query"] == query


def test_query_timer_error():
    """Test QueryTimer with error."""
    from harness.data.query_tracer import get_query_tracer

    tracer = get_query_tracer()
    query = "SELECT * FROM users"

    with pytest.raises(ValueError):
        with QueryTimer(query):
            raise ValueError("test error")

    traces = tracer.get_recent_traces()
    assert len(traces) >= 1
    assert traces[-1]["success"] is False


def test_trace_query_helper():
    """Test trace_query helper function."""
    import time

    with trace_query("SELECT * FROM users"):
        time.sleep(0.01)

    tracer = get_query_tracer()
    traces = tracer.get_recent_traces()
    assert len(traces) >= 1


def test_query_tracer_max_traces():
    """Test QueryTracer max traces limit."""
    tracer = QueryTracer(max_traces=5)

    for i in range(10):
        tracer.trace_query(f"SELECT {i}", 10.0, True)

    traces = tracer.get_recent_traces()
    assert len(traces) == 5
