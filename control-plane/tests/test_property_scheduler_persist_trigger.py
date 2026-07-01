"""Property-based test for Scheduler persistence and time-triggering.

# Feature: orchestration-engine-completion, Property 34: Scheduled tasks persist and trigger only when active

Property 34 states that *for any* Scheduled_Task created in an active or paused
state:

* **Persistence (Req 14.1).** The association of a Workflow_Definition with its
  schedule persists with its state and survives a reload — a brand-new
  ``Scheduler`` opened over the same database reads back the same tasks with the
  same ``definition_id``, ``cron_expression``, and ``state``.
* **Trigger on match (Req 14.2).** On a ``tick`` driven by a fixed mock clock, an
  *active* task starts exactly one Workflow_Run if and only if its schedule
  matches the clock instant.
* **Paused tasks never trigger (Req 14.3).** A *paused* task never starts a run,
  regardless of whether its schedule matches the clock instant.

The test drives the Scheduler with a fixed (mock) clock and generates random
cron expressions, random active/paused states, and a random tick instant. The
expected schedule match for each task is computed *independently* with
:class:`~core.cron_parser.CronParser`, so the Scheduler's own matching logic is
never trusted to define the oracle. A temporary SQLite database and a recording
executor make every example deterministic and side-effect free.

**Validates: Requirements 14.1, 14.2, 14.3**
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.cron_parser import CronParser, Schedule
from core.database import SQLiteBackend
from core.scheduler import STATE_ACTIVE, STATE_PAUSED, Scheduler

# ---------------------------------------------------------------------------
# Independent oracle: does ``moment`` match ``schedule``?
# ---------------------------------------------------------------------------


def _cron_dow(moment: datetime) -> int:
    """Convert a Python weekday (Mon=0) to a cron day-of-week (Sun=0)."""
    return (moment.weekday() + 1) % 7


def _expected_match(schedule: Schedule, moment: datetime) -> bool:
    """Independent reimplementation of cron matching used as the oracle.

    Computed straight from a :class:`Schedule` parsed by :class:`CronParser`,
    deliberately *not* calling into the Scheduler, so the test's expectations do
    not depend on the code under test.
    """
    return (
        moment.minute in schedule.minute
        and moment.hour in schedule.hour
        and moment.day in schedule.day_of_month
        and moment.month in schedule.month
        and _cron_dow(moment) in schedule.day_of_week
    )


# ---------------------------------------------------------------------------
# Strategies: a fixed clock instant + random scheduled tasks
# ---------------------------------------------------------------------------


@st.composite
def _moments(draw: st.DrawFn) -> datetime:
    """A fixed, timezone-aware UTC instant. Days are kept in 1..28 so every
    generated (year, month, day) tuple is a real calendar date."""
    return datetime(
        year=draw(st.integers(min_value=2020, max_value=2035)),
        month=draw(st.integers(min_value=1, max_value=12)),
        day=draw(st.integers(min_value=1, max_value=28)),
        hour=draw(st.integers(min_value=0, max_value=23)),
        minute=draw(st.integers(min_value=0, max_value=59)),
        tzinfo=timezone.utc,
    )


def _rich_field(low: int, high: int, matching: int) -> st.SearchStrategy[str]:
    """A cron field token for minute/hour/day-of-week.

    Biased toward ``*`` and the value that matches ``moment`` so the
    "active task triggers" branch is exercised often, while still drawing
    arbitrary in-range values (and small lists) to cover the non-matching
    branch."""
    values = st.integers(min_value=low, max_value=high)
    lists = st.lists(values, min_size=2, max_size=3, unique=True).map(
        lambda vs: ",".join(str(v) for v in sorted(vs))
    )
    return st.one_of(
        st.just("*"),
        st.just(str(matching)),  # guarantees this field matches
        values.map(str),  # arbitrary in-range value
        lists,  # a small value list
    )


@st.composite
def _tasks(draw: st.DrawFn, moment: datetime) -> dict[str, Any]:
    """A single scheduled task: a valid cron expression plus active/paused state.

    The day-of-month and month fields are restricted to ``*`` or the value that
    matches ``moment``; this keeps every generated schedule reachable from the
    clock so the active-task ``next_run_at`` forward scan stays cheap, while the
    minute/hour/day-of-week fields still freely cover matching and non-matching
    instants."""
    minute = draw(_rich_field(0, 59, moment.minute))
    hour = draw(_rich_field(0, 23, moment.hour))
    dom = draw(st.one_of(st.just("*"), st.just(str(moment.day))))
    month = draw(st.one_of(st.just("*"), st.just(str(moment.month))))
    dow = draw(_rich_field(0, 6, _cron_dow(moment)))
    expression = f"{minute} {hour} {dom} {month} {dow}"
    state = draw(st.sampled_from([STATE_ACTIVE, STATE_PAUSED]))
    return {"cron_expression": expression, "state": state}


@st.composite
def _cases(draw: st.DrawFn) -> dict[str, Any]:
    """A fixed clock instant plus a small batch of scheduled tasks."""
    moment = draw(_moments())
    size = draw(st.integers(min_value=1, max_value=4))
    tasks = [draw(_tasks(moment)) for _ in range(size)]
    return {"moment": moment, "tasks": tasks}


# ---------------------------------------------------------------------------
# Recording executor (fixed-clock driven, deterministic)
# ---------------------------------------------------------------------------


class _RecordingExecutor:
    """Fake DagExecutor recording the definition_ids it was asked to run."""

    def __init__(self) -> None:
        self.started: list[str] = []

    def start_run(self, definition_id: str) -> str:
        run_id = f"run-{len(self.started)}-{definition_id}"
        self.started.append(definition_id)
        return run_id


# ---------------------------------------------------------------------------
# Property 34
# ---------------------------------------------------------------------------


@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(case=_cases())
def test_scheduled_tasks_persist_and_trigger_only_when_active(
    case: dict[str, Any],
) -> None:
    moment: datetime = case["moment"]
    task_specs: list[dict[str, Any]] = case["tasks"]
    parser = CronParser()

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "scheduler-prop.db"

        # -- Create tasks against a first Scheduler driven by a fixed clock.
        backend = SQLiteBackend(db_path)
        creator = Scheduler(backend, _RecordingExecutor(), clock=lambda: moment)

        created: list[dict[str, Any]] = []
        for index, spec in enumerate(task_specs):
            task = creator.create(
                f"def-{index}",
                spec["cron_expression"],
                state=spec["state"],
            )
            created.append(task)

        # -- Req 14.1: a brand-new Scheduler over the SAME database reads the
        # tasks back with their state, definition, and schedule intact.
        reloaded_backend = SQLiteBackend(db_path)
        executor = _RecordingExecutor()
        reloaded = Scheduler(reloaded_backend, executor, clock=lambda: moment)

        for task in created:
            persisted = reloaded.get(task["id"])
            assert persisted is not None, "task did not survive reload"
            assert persisted["definition_id"] == task["definition_id"]
            assert persisted["cron_expression"] == task["cron_expression"]
            assert persisted["state"] == task["state"]

        # -- Tick the reloaded Scheduler at the fixed clock instant.
        reloaded.tick(moment)

        # Independent oracle: which definitions *should* have triggered?
        # Req 14.2: an active task triggers iff its schedule matches `moment`.
        # Req 14.3: a paused task never triggers, even when its schedule matches.
        expected_started: set[str] = set()
        for task in created:
            schedule = parser.parse(task["cron_expression"])
            matches = _expected_match(schedule, moment)
            if task["state"] == STATE_ACTIVE and matches:
                expected_started.add(task["definition_id"])
            elif task["state"] == STATE_PAUSED:
                # Explicitly assert the paused task is absent regardless of match.
                assert task["definition_id"] not in set(executor.started)

        # Definition ids are unique per task, so each triggers at most once.
        assert set(executor.started) == expected_started
        assert len(executor.started) == len(expected_started)
