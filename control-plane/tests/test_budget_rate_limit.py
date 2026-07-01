"""Unit tests for BudgetTracker and RateLimiter (task 16.1).

Covers cumulative usage tracking and blocking (Req 7.1, 7.2), fail-open when
budget state is unavailable (Req 7.3), sliding-window rate limiting with delay
(Req 7.4), and the status events emitted on block/skip/delay (Req 7.5). Both the
budget-state source and the rate-limiter clock are injectable so tests run
without touching real time.

Property tests for these behaviours live in their own files (tasks 16.2-16.4).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.database import SQLiteBackend
from core.event_router import EventRouter, WorkflowEventType
from core.inference_gateway import (
    BudgetExceededError,
    BudgetTracker,
    InferenceGateway,
    ModelResponse,
    RateLimiter,
)
from core.orchestration_types import Budget, ModelRequest, RoutingPolicy, RunScope, RunState
from core.provider_router import ProviderRouter


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def backend(tmp_path: Path) -> SQLiteBackend:
    return SQLiteBackend(tmp_path / "budget-test.db")


@pytest.fixture()
def events(backend: SQLiteBackend) -> EventRouter:
    return EventRouter(backend)


def _insert_run(backend: SQLiteBackend, run_id: str = "run-1") -> None:
    backend.execute(
        "INSERT INTO workflow_runs "
        "(id, definition_id, state, concurrency_limit, budget_json, "
        "created_at, started_at, finished_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, "def-1", RunState.RUNNING.value, 1, None, "2024-01-01T00:00:00Z", None, None),
    )


def _scope(budget: Budget | None = None, run_id: str = "run-1") -> RunScope:
    return RunScope(run_id=run_id, definition_id="def-1", budget=budget)


class _FakeClock:
    """A controllable monotonic clock; sleeping advances the fake time."""

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


# ---------------------------------------------------------------------------
# BudgetTracker — tracking and blocking (Req 7.1, 7.2)
# ---------------------------------------------------------------------------


def test_charge_accumulates_usage_on_scope_budget(backend, events):
    budget = Budget(max_tokens=100, max_cost=1.0)
    tracker = BudgetTracker(backend, events)
    scope = _scope(budget)

    tracker.charge(scope, tokens=10, cost=0.1)
    tracker.charge(scope, tokens=5, cost=0.05)

    assert budget.used_tokens == 15
    assert budget.used_cost == pytest.approx(0.15)


def test_precheck_allows_when_within_budget(backend, events):
    tracker = BudgetTracker(backend, events)
    scope = _scope(Budget(max_tokens=100))

    decision = tracker.precheck(scope, tokens=50)

    assert decision.allowed is True
    assert decision.fail_open is False


def test_precheck_allows_when_no_budget_configured(backend, events):
    tracker = BudgetTracker(backend, events)
    decision = tracker.precheck(_scope(None), tokens=10_000)
    assert decision.allowed is True
    assert decision.fail_open is False


def test_precheck_blocks_and_transitions_run_on_token_exceed(backend, events):
    _insert_run(backend)
    tracker = BudgetTracker(backend, events)
    scope = _scope(Budget(max_tokens=100, used_tokens=90))

    with pytest.raises(BudgetExceededError) as exc_info:
        tracker.precheck(scope, tokens=20)

    assert exc_info.value.run_id == "run-1"
    # Req 7.2: run transitioned to the budget_exceeded terminal state.
    row = backend.fetch_one("SELECT state FROM workflow_runs WHERE id = ?", ("run-1",))
    assert row["state"] == RunState.BUDGET_EXCEEDED.value
    # Req 7.5: a budget status event records the block.
    history = events.history("run-1")
    assert any(
        e.type == WorkflowEventType.BUDGET_STATUS and e.payload.get("blocked")
        for e in history
    )


def test_precheck_blocks_on_cost_exceed(backend, events):
    _insert_run(backend)
    tracker = BudgetTracker(backend, events)
    scope = _scope(Budget(max_cost=1.0, used_cost=0.95))

    with pytest.raises(BudgetExceededError):
        tracker.precheck(scope, cost=0.10)


# ---------------------------------------------------------------------------
# BudgetTracker — fail-open (Req 7.3)
# ---------------------------------------------------------------------------


def test_precheck_fails_open_when_state_unavailable(backend, events):
    def broken_provider(_scope: RunScope) -> Budget | None:
        raise RuntimeError("budget store unavailable")

    tracker = BudgetTracker(backend, events, budget_state_provider=broken_provider)

    decision = tracker.precheck(_scope(Budget(max_tokens=1)), tokens=1000)

    # Req 7.3: proceed, disable rate-limit delays, record the skipped check.
    assert decision.allowed is True
    assert decision.fail_open is True
    assert decision.skip_rate_limit is True
    history = events.history("run-1")
    assert any(
        e.type == WorkflowEventType.BUDGET_STATUS and e.payload.get("skipped")
        for e in history
    )


def test_precheck_loads_budget_from_persistence(backend, events):
    # Persisted budget already over the limit; scope carries no in-memory budget.
    backend.execute(
        "INSERT INTO workflow_runs "
        "(id, definition_id, state, concurrency_limit, budget_json, "
        "created_at, started_at, finished_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "run-db",
            "def-1",
            RunState.RUNNING.value,
            1,
            '{"max_tokens": 100, "max_cost": null, "used_tokens": 95, "used_cost": 0.0}',
            "2024-01-01T00:00:00Z",
            None,
            None,
        ),
    )
    tracker = BudgetTracker(backend, events)
    scope = _scope(None, run_id="run-db")

    with pytest.raises(BudgetExceededError):
        tracker.precheck(scope, tokens=10)


def test_charge_persists_usage_to_database(backend, events):
    backend.execute(
        "INSERT INTO workflow_runs "
        "(id, definition_id, state, concurrency_limit, budget_json, "
        "created_at, started_at, finished_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "run-db",
            "def-1",
            RunState.RUNNING.value,
            1,
            '{"max_tokens": 100, "max_cost": null, "used_tokens": 0, "used_cost": 0.0}',
            "2024-01-01T00:00:00Z",
            None,
            None,
        ),
    )
    tracker = BudgetTracker(backend, events)
    tracker.charge(_scope(None, run_id="run-db"), tokens=30, cost=0.0)

    row = backend.fetch_one("SELECT budget_json FROM workflow_runs WHERE id = ?", ("run-db",))
    assert '"used_tokens": 30' in row["budget_json"]


# ---------------------------------------------------------------------------
# RateLimiter — windowing and delay (Req 7.4, 7.5)
# ---------------------------------------------------------------------------


def test_rate_limiter_admits_up_to_max_without_delay(backend, events):
    clock = _FakeClock()
    limiter = RateLimiter(
        events, max_calls=3, window_seconds=10.0, clock=clock.time, sleep=clock.sleep
    )
    scope = _scope()

    delays = [limiter.acquire(scope, "p") for _ in range(3)]

    assert delays == [0.0, 0.0, 0.0]
    assert clock.slept == []


def test_rate_limiter_delays_excess_until_window_frees(backend, events):
    clock = _FakeClock()
    limiter = RateLimiter(
        events, max_calls=2, window_seconds=10.0, clock=clock.time, sleep=clock.sleep
    )
    scope = _scope()

    limiter.acquire(scope, "p")  # t=0
    limiter.acquire(scope, "p")  # t=0
    delay = limiter.acquire(scope, "p")  # window full -> wait 10s

    assert delay == pytest.approx(10.0)
    assert clock.slept == [pytest.approx(10.0)]
    # Req 7.5: a rate-limit status event was emitted for the delay.
    history = events.history("run-1")
    assert any(e.type == WorkflowEventType.RATE_LIMIT_STATUS for e in history)


def test_rate_limiter_is_per_provider(backend, events):
    clock = _FakeClock()
    limiter = RateLimiter(
        events, max_calls=1, window_seconds=10.0, clock=clock.time, sleep=clock.sleep
    )
    scope = _scope()

    assert limiter.acquire(scope, "a") == 0.0
    # A different provider has its own window and is not delayed.
    assert limiter.acquire(scope, "b") == 0.0
    assert clock.slept == []


def test_rate_limiter_noop_when_unconfigured(backend, events):
    clock = _FakeClock()
    limiter = RateLimiter(
        events, max_calls=0, window_seconds=0.0, clock=clock.time, sleep=clock.sleep
    )
    for _ in range(100):
        assert limiter.acquire(_scope(), "p") == 0.0
    assert clock.slept == []


# ---------------------------------------------------------------------------
# Gateway integration
# ---------------------------------------------------------------------------


def _gateway(events, provider_call, *, budgets=None, limiter=None, cost_estimator=None, policy=None):
    return InferenceGateway(
        ProviderRouter(),
        events,
        provider_call=provider_call,
        default_policy=policy or RoutingPolicy(fallback_order=["a"]),
        budgets=budgets,
        limiter=limiter,
        cost_estimator=cost_estimator,
        sleep=lambda _s: None,
    )


def test_gateway_blocks_call_when_budget_exceeded(backend, events):
    _insert_run(backend)
    calls: list[str] = []

    def provider_call(pid, req, scope):
        calls.append(pid)
        return ModelResponse(text="ok", provider_id=pid)

    tracker = BudgetTracker(backend, events)
    gateway = _gateway(
        events,
        provider_call,
        budgets=tracker,
        cost_estimator=lambda _req: (50, 0.0),
    )
    scope = _scope(Budget(max_tokens=100, used_tokens=90))

    with pytest.raises(BudgetExceededError):
        gateway.call(ModelRequest(messages=[]), scope)

    # The provider was never invoked because the call was blocked.
    assert calls == []


def test_gateway_charges_budget_after_successful_call(backend, events):
    tracker = BudgetTracker(backend, events)
    budget = Budget(max_tokens=1000)
    gateway = _gateway(
        events,
        lambda pid, req, scope: ModelResponse(text="ok", provider_id=pid, token_usage=42),
        budgets=tracker,
        cost_estimator=lambda _req: (10, 0.0),
    )
    scope = _scope(budget)

    gateway.call(ModelRequest(messages=[]), scope)

    # Actual token usage from the response is charged (not the estimate).
    assert budget.used_tokens == 42


def test_gateway_fail_open_disables_rate_limit(backend, events):
    def broken_provider(_scope: RunScope) -> Budget | None:
        raise RuntimeError("unavailable")

    tracker = BudgetTracker(backend, events, budget_state_provider=broken_provider)

    acquired: list[str] = []

    class _SpyLimiter(RateLimiter):
        def acquire(self, scope, provider_id):  # type: ignore[override]
            acquired.append(provider_id)
            return 0.0

    limiter = _SpyLimiter(events, max_calls=1, window_seconds=10.0)
    gateway = _gateway(
        events,
        lambda pid, req, scope: ModelResponse(text="ok", provider_id=pid),
        budgets=tracker,
        limiter=limiter,
        cost_estimator=lambda _req: (10, 0.0),
    )

    response = gateway.call(ModelRequest(messages=[]), _scope(Budget(max_tokens=1)))

    assert response.text == "ok"
    # Req 7.3: rate-limit delays disabled for the fail-open call.
    assert acquired == []


def test_gateway_applies_rate_limit_when_budget_ok(backend, events):
    tracker = BudgetTracker(backend, events)
    acquired: list[str] = []

    class _SpyLimiter(RateLimiter):
        def acquire(self, scope, provider_id):  # type: ignore[override]
            acquired.append(provider_id)
            return 0.0

    limiter = _SpyLimiter(events, max_calls=10, window_seconds=10.0)
    gateway = _gateway(
        events,
        lambda pid, req, scope: ModelResponse(text="ok", provider_id=pid),
        budgets=tracker,
        limiter=limiter,
        cost_estimator=lambda _req: (10, 0.0),
    )

    gateway.call(ModelRequest(messages=[]), _scope(Budget(max_tokens=1000)))

    assert acquired == ["a"]
