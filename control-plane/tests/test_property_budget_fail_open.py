"""Property-based test for Budget fail-open on unavailable budget state.

# Feature: orchestration-engine-completion, Property 21: Budget-state unavailability fails open and is recorded

Property 21 states that *for any* model call where budget state is temporarily
unavailable, :meth:`BudgetTracker.precheck`:

* never raises (the call is always allowed to proceed),
* returns a decision with ``allowed=True``, ``fail_open=True``, and
  ``skip_rate_limit=True`` (so the gateway disables Rate_Limit delays for the
  call), and
* records the skipped Budget check in the Workflow_Run event history as a
  ``BUDGET_STATUS`` event whose payload marks it ``skipped`` (Req 7.3).

The test generates random run scopes (run/definition ids, with or without an
in-memory Budget) and random estimated token/cost amounts, paired with a
``budget_state_provider`` that *always raises* to simulate unavailable budget
state. Each example asserts all three invariants above against a temporary
SQLite-backed :class:`EventRouter`.

**Validates: Requirements 7.3**
"""

from __future__ import annotations

import string
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.database import SQLiteBackend
from core.event_router import EventRouter, WorkflowEventType
from core.inference_gateway import BudgetTracker
from core.orchestration_types import Budget, RunScope


# ---------------------------------------------------------------------------
# Fixtures: a temporary SQLite-backed EventRouter shared across examples.
# ---------------------------------------------------------------------------


@pytest.fixture()
def backend(tmp_path: Path) -> SQLiteBackend:
    return SQLiteBackend(tmp_path / "budget-fail-open.db")


@pytest.fixture()
def events(backend: SQLiteBackend) -> EventRouter:
    return EventRouter(backend)


# ---------------------------------------------------------------------------
# Strategies: random scopes and estimated amounts.
# ---------------------------------------------------------------------------

_IDENT = st.text(
    alphabet=string.ascii_letters + string.digits + "_-", min_size=1, max_size=12
)

# Optional in-memory Budget: fail-open must hold whether or not the scope
# carries a Budget, since the failure happens while *loading* budget state.
_BUDGETS = st.one_of(
    st.none(),
    st.builds(
        Budget,
        max_tokens=st.one_of(st.none(), st.integers(min_value=0, max_value=1_000_000)),
        max_cost=st.one_of(st.none(), st.floats(min_value=0.0, max_value=1_000.0)),
        used_tokens=st.integers(min_value=0, max_value=1_000_000),
        used_cost=st.floats(min_value=0.0, max_value=1_000.0),
    ),
)


@st.composite
def scopes(draw: st.DrawFn) -> RunScope:
    return RunScope(
        run_id=draw(_IDENT),
        definition_id=draw(_IDENT),
        budget=draw(_BUDGETS),
    )


# ---------------------------------------------------------------------------
# Property 21
# ---------------------------------------------------------------------------


# A single temporary SQLite-backed EventRouter is shared across all examples
# (suppress_health_check below). Reuse is safe: each example queries the run
# history for its own run_id, and every recorded event is a skipped-check event.
@settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    scope=scopes(),
    tokens=st.integers(min_value=0, max_value=10_000_000),
    cost=st.floats(min_value=0.0, max_value=1_000_000.0),
    reason=st.text(max_size=40),
)
def test_budget_fail_open_proceeds_and_records_skip(
    backend: SQLiteBackend,
    events: EventRouter,
    scope: RunScope,
    tokens: int,
    cost: float,
    reason: str,
) -> None:
    # A provider that always raises => budget state is unavailable.
    def broken_provider(_scope: RunScope) -> Budget | None:
        raise RuntimeError(reason or "budget store unavailable")

    tracker = BudgetTracker(backend, events, budget_state_provider=broken_provider)

    # -- Invariant 1: precheck never raises; the call is allowed to proceed.
    decision = tracker.precheck(scope, tokens=tokens, cost=cost)

    # -- Invariant 2: fail-open decision disables rate-limit delays (Req 7.3).
    assert decision.allowed is True
    assert decision.fail_open is True
    assert decision.skip_rate_limit is True

    # -- Invariant 3: the skipped Budget check is recorded in the run history.
    history = events.history(scope.run_id)
    assert any(
        e.type == WorkflowEventType.BUDGET_STATUS and e.payload.get("skipped")
        for e in history
    )
