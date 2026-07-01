"""Unit tests for the Scheduler core (task 25.1).

Covers persistence of Workflow_Definition↔schedule associations in active or
paused state (Req 14.1), starting a run when the clock matches an active task
(Req 14.2), never triggering a paused task (Req 14.3), and rejecting invalid
schedule expressions with a descriptive error via the Cron_Parser (Req 14.5).

These are example-based unit tests with a deterministic, injectable clock and a
recording fake DagExecutor. Property tests (25.2, 25.3) live in their own files.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.cron_parser import CronParseError
from core.database import SQLiteBackend
from core.scheduler import (
    STATE_ACTIVE,
    STATE_PAUSED,
    Scheduler,
    SchedulerError,
)


class _RecordingExecutor:
    """Fake DagExecutor that records start_run calls and returns run ids."""

    def __init__(self) -> None:
        self.started: list[str] = []

    def start_run(self, definition_id: str) -> str:
        run_id = f"run-{len(self.started)}-{definition_id}"
        self.started.append(definition_id)
        return run_id


@pytest.fixture()
def backend(tmp_path: Path) -> SQLiteBackend:
    return SQLiteBackend(tmp_path / "scheduler-test.db")


@pytest.fixture()
def executor() -> _RecordingExecutor:
    return _RecordingExecutor()


def _clock(moment: datetime):
    return lambda: moment


# A Monday: 2024-01-01 00:00 UTC is a Monday (cron dow == 1).
_MONDAY_MIDNIGHT = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# create — Req 14.1, 14.5
# ---------------------------------------------------------------------------


def test_create_persists_active_association(backend, executor):
    sched = Scheduler(backend, executor, clock=_clock(_MONDAY_MIDNIGHT))
    task = sched.create("def-1", "* * * * *")

    assert task["definition_id"] == "def-1"
    assert task["cron_expression"] == "* * * * *"
    assert task["state"] == STATE_ACTIVE
    # Round-trips through persistence.
    assert sched.get(task["id"]) == task


def test_create_persists_paused_association(backend, executor):
    sched = Scheduler(backend, executor, clock=_clock(_MONDAY_MIDNIGHT))
    task = sched.create("def-1", "0 9 * * *", state=STATE_PAUSED)

    assert task["state"] == STATE_PAUSED
    # A paused task records no next run time.
    assert task["next_run_at"] is None


def test_create_active_records_next_run(backend, executor):
    sched = Scheduler(backend, executor, clock=_clock(_MONDAY_MIDNIGHT))
    task = sched.create("def-1", "* * * * *")
    assert task["next_run_at"] is not None


def test_create_rejects_invalid_expression_without_persisting(backend, executor):
    sched = Scheduler(backend, executor, clock=_clock(_MONDAY_MIDNIGHT))
    with pytest.raises(CronParseError):
        sched.create("def-1", "not a cron")
    # Nothing persisted for the rejected expression (Req 14.5).
    assert sched.list_tasks() == []


def test_create_rejects_invalid_state(backend, executor):
    sched = Scheduler(backend, executor, clock=_clock(_MONDAY_MIDNIGHT))
    with pytest.raises(SchedulerError):
        sched.create("def-1", "* * * * *", state="bogus")


# ---------------------------------------------------------------------------
# tick — Req 14.2, 14.3
# ---------------------------------------------------------------------------


def test_tick_starts_run_when_clock_matches_active_task(backend, executor):
    sched = Scheduler(backend, executor, clock=_clock(_MONDAY_MIDNIGHT))
    sched.create("def-1", "0 0 1 1 *")  # midnight Jan 1

    started = sched.tick(_MONDAY_MIDNIGHT)

    assert len(started) == 1
    assert executor.started == ["def-1"]


def test_tick_does_not_start_when_clock_does_not_match(backend, executor):
    sched = Scheduler(backend, executor, clock=_clock(_MONDAY_MIDNIGHT))
    sched.create("def-1", "30 9 * * *")  # 09:30 daily

    started = sched.tick(_MONDAY_MIDNIGHT)

    assert started == []
    assert executor.started == []


def test_tick_never_triggers_paused_task(backend, executor):
    sched = Scheduler(backend, executor, clock=_clock(_MONDAY_MIDNIGHT))
    task = sched.create("def-1", "* * * * *")  # matches every minute
    sched.pause(task["id"])

    started = sched.tick(_MONDAY_MIDNIGHT)

    assert started == []
    assert executor.started == []


def test_resume_allows_triggering_again(backend, executor):
    sched = Scheduler(backend, executor, clock=_clock(_MONDAY_MIDNIGHT))
    task = sched.create("def-1", "* * * * *")
    sched.pause(task["id"])
    assert sched.tick(_MONDAY_MIDNIGHT) == []

    sched.resume(task["id"])
    started = sched.tick(_MONDAY_MIDNIGHT)

    assert len(started) == 1
    assert executor.started == ["def-1"]


def test_tick_uses_injected_clock_by_default(backend, executor):
    sched = Scheduler(backend, executor, clock=_clock(_MONDAY_MIDNIGHT))
    sched.create("def-1", "0 0 1 1 *")

    started = sched.tick()  # no explicit now -> uses clock

    assert len(started) == 1


def test_tick_matches_day_of_week(backend, executor):
    # _MONDAY_MIDNIGHT is a Monday -> cron dow 1.
    sched = Scheduler(backend, executor, clock=_clock(_MONDAY_MIDNIGHT))
    sched.create("monday", "0 0 * * 1")
    sched.create("sunday", "0 0 * * 0")

    started = sched.tick(_MONDAY_MIDNIGHT)

    assert executor.started == ["monday"]
    assert len(started) == 1


def test_tick_starts_multiple_due_tasks(backend, executor):
    sched = Scheduler(backend, executor, clock=_clock(_MONDAY_MIDNIGHT))
    sched.create("def-a", "* * * * *")
    sched.create("def-b", "0 0 * * *")

    started = sched.tick(_MONDAY_MIDNIGHT)

    assert len(started) == 2
    assert set(executor.started) == {"def-a", "def-b"}


# ---------------------------------------------------------------------------
# pause / resume / queries
# ---------------------------------------------------------------------------


def test_pause_unknown_task_raises(backend, executor):
    sched = Scheduler(backend, executor, clock=_clock(_MONDAY_MIDNIGHT))
    with pytest.raises(SchedulerError):
        sched.pause("missing")


def test_list_tasks_filters_by_definition(backend, executor):
    sched = Scheduler(backend, executor, clock=_clock(_MONDAY_MIDNIGHT))
    sched.create("def-1", "* * * * *")
    sched.create("def-2", "* * * * *")

    assert len(sched.list_tasks()) == 2
    assert len(sched.list_tasks(definition_id="def-1")) == 1
