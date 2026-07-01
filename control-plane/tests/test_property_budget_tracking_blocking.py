"""Property-based test for budget tracking accuracy and blocking on exceed.

# Feature: orchestration-engine-completion, Property 20: Budget tracking is accurate and blocks on exceed

Property 20 states that *for any* configured Budget (token and/or cost limits)
and *any* sequence of charges and prechecks, the :class:`BudgetTracker` upholds
two invariants:

* **Accurate tracking (Req 7.1).** After applying a sequence of charges, the
  cumulative tracked usage (both in memory and persisted to
  ``workflow_runs.budget_json``) equals the exact sum of the charged tokens and
  costs.
* **Block on exceed (Req 7.2).** A precheck whose estimated usage would carry
  the run over either configured limit is blocked: it raises
  :class:`BudgetExceededError`, transitions the run to the ``budget_exceeded``
  terminal state, and emits a blocking ``budget.status`` event. A precheck that
  stays within both limits is allowed and leaves the run state unchanged.

The test generates random token/cost limits and a random sequence of
charge/precheck operations against a temp SQLite-backed run row and a real
:class:`EventRouter`. An independent oracle mirrors the cumulative usage and the
``would_exceed`` decision so the tracker's behavior is checked against a simple
reference at every step.

Costs are generated as whole numbers so the oracle's float arithmetic is exact
and never disagrees with the tracker at a limit boundary.

**Validates: Requirements 7.1, 7.2**
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.database import SQLiteBackend
from core.event_router import EventRouter, WorkflowEventType
from core.inference_gateway import BudgetExceededError, BudgetTracker
from core.orchestration_types import Budget, RunScope, RunState

# ---------------------------------------------------------------------------
# Strategies: random budget limits + a sequence of charge/precheck operations
# ---------------------------------------------------------------------------

# A dimension limit is either unbounded (None) or a small positive bound so that
# prechecks realistically reach the limit within a short operation sequence.
_TOKEN_LIMIT = st.one_of(st.none(), st.integers(min_value=1, max_value=500))
_COST_LIMIT = st.one_of(st.none(), st.integers(min_value=1, max_value=500))

# Per-operation amounts. Costs are whole numbers (carried as floats) so the
# oracle's running sum is exact and matches ``would_exceed`` at the boundary.
_AMOUNT = st.integers(min_value=0, max_value=200)


@st.composite
def budget_cases(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a budget config plus a random charge/precheck sequence."""
    max_tokens = draw(_TOKEN_LIMIT)
    max_cost = draw(_COST_LIMIT)
    size = draw(st.integers(min_value=1, max_value=12))
    ops: list[dict[str, Any]] = []
    for _ in range(size):
        ops.append(
            {
                "kind": draw(st.sampled_from(["charge", "precheck"])),
                "tokens": draw(_AMOUNT),
                "cost": draw(_AMOUNT),
            }
        )
    return {"max_tokens": max_tokens, "max_cost": max_cost, "ops": ops}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_run(backend: SQLiteBackend, run_id: str) -> None:
    backend.execute(
        "INSERT INTO workflow_runs "
        "(id, definition_id, state, concurrency_limit, budget_json, "
        "created_at, started_at, finished_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, "def-1", RunState.RUNNING.value, 1, None, "2024-01-01T00:00:00Z", None, None),
    )


def _run_state(backend: SQLiteBackend, run_id: str) -> str:
    row = backend.fetch_one("SELECT state FROM workflow_runs WHERE id = ?", (run_id,))
    assert row is not None
    return row["state"]


def _has_block_event(events: EventRouter, run_id: str) -> bool:
    return any(
        e.type == WorkflowEventType.BUDGET_STATUS and e.payload.get("blocked")
        for e in events.history(run_id)
    )


# ---------------------------------------------------------------------------
# Property 20
# ---------------------------------------------------------------------------


@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(case=budget_cases())
def test_budget_tracking_is_accurate_and_blocks_on_exceed(case: dict[str, Any]) -> None:
    max_tokens: int | None = case["max_tokens"]
    max_cost: int | None = case["max_cost"]
    ops: list[dict[str, Any]] = case["ops"]

    run_id = "run-prop-20"
    with tempfile.TemporaryDirectory() as tmp:
        backend = SQLiteBackend(Path(tmp) / "budget-prop.db")
        _insert_run(backend, run_id)
        events = EventRouter(backend)
        tracker = BudgetTracker(backend, events)

        budget = Budget(max_tokens=max_tokens, max_cost=max_cost)
        scope = RunScope(run_id=run_id, definition_id="def-1", budget=budget)

        # Oracle mirrors cumulative usage actually charged.
        used_tokens = 0
        used_cost = 0.0
        blocked = False

        for op in ops:
            tokens = op["tokens"]
            cost = float(op["cost"])

            if op["kind"] == "charge":
                tracker.charge(scope, tokens=tokens, cost=cost)
                used_tokens += tokens
                used_cost += cost

                # Req 7.1: in-memory cumulative usage equals the sum of charges.
                assert budget.used_tokens == used_tokens
                assert budget.used_cost == pytest.approx(used_cost)
                continue

            # precheck: decide expected outcome from the oracle.
            would_exceed = (
                max_tokens is not None and used_tokens + tokens > max_tokens
            ) or (max_cost is not None and used_cost + cost > max_cost)

            if would_exceed:
                # Req 7.2: blocked — raises, transitions run, emits status.
                with pytest.raises(BudgetExceededError) as exc_info:
                    tracker.precheck(scope, tokens=tokens, cost=cost)
                assert exc_info.value.run_id == run_id
                assert _run_state(backend, run_id) == RunState.BUDGET_EXCEEDED.value
                assert _has_block_event(events, run_id)
                blocked = True
                # The run is now terminal; stop applying further operations so
                # the "allowed leaves state unchanged" check stays meaningful.
                break

            # Within limits: allowed, no state change, usage untouched.
            decision = tracker.precheck(scope, tokens=tokens, cost=cost)
            assert decision.allowed is True
            assert decision.fail_open is False
            assert _run_state(backend, run_id) == RunState.RUNNING.value
            assert budget.used_tokens == used_tokens
            assert budget.used_cost == pytest.approx(used_cost)

        # Req 7.1: persisted usage matches the oracle when any charge occurred
        # and the run was not blocked (a block overwrites budget_json on exit).
        if not blocked and (used_tokens > 0 or used_cost > 0):
            row = backend.fetch_one(
                "SELECT budget_json FROM workflow_runs WHERE id = ?", (run_id,)
            )
            assert row is not None and row["budget_json"]
            from core.helpers import from_json

            persisted = from_json(row["budget_json"], {})
            assert int(persisted["used_tokens"]) == used_tokens
            assert float(persisted["used_cost"]) == pytest.approx(used_cost)
