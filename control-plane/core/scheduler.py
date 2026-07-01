"""Scheduler — time-triggered Workflow_Runs from persisted Scheduled_Tasks.

The Scheduler is the Control_Plane subsystem that triggers Workflow_Runs on a
time schedule (Requirement 14). It owns four responsibilities, each mapped to an
acceptance criterion:

* **Persist associations (Requirement 14.1)** — :meth:`Scheduler.create`
  validates a cron expression with :class:`~core.cron_parser.CronParser` and
  persists the association of a Workflow_Definition with its schedule. A
  Scheduled_Task may be created in either an ``active`` or a ``paused`` state.
* **Trigger on match (Requirement 14.2)** — :meth:`Scheduler.tick` evaluates
  every *active* task against its :class:`~core.cron_parser.Schedule` and starts
  a Workflow_Run via :meth:`~core.dag_executor.DagExecutor.start_run` for each
  task whose schedule matches the current time.
* **Paused tasks never trigger (Requirement 14.3)** — :meth:`tick` only
  considers tasks in the ``active`` state, so a paused task never starts a run
  until :meth:`Scheduler.resume` reactivates it.
* **Reject invalid expressions (Requirement 14.5)** — invalid schedule
  expressions are rejected by :meth:`create` with the descriptive
  :class:`~core.cron_parser.CronParseError` raised by the Cron_Parser; no row is
  persisted for an unparseable expression.

Persistence uses the schema declared in ``core/database.py``::

    scheduled_tasks(id, definition_id, cron_expression, state, next_run_at,
                    created_at, updated_at)

Schedule matching follows the canonical 5-field cron semantics: a task is *due*
when the current time's minute, hour, day-of-month, month, and day-of-week all
fall within the corresponding value sets of its parsed
:class:`~core.cron_parser.Schedule`. The clock is injectable so the trigger loop
is fully deterministic under test.

Identifiers are UUID4 strings and timestamps come from ``core.helpers.now_iso``,
matching the conventions used by the other Control_Plane services.
"""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from core.cron_parser import CronParser, Schedule
from core.database import DatabaseBackend
from core.helpers import now_iso

LOGGER = logging.getLogger("vloop.control_plane.scheduler")

# Scheduled_Task lifecycle states.
STATE_ACTIVE = "active"
STATE_PAUSED = "paused"
_VALID_STATES = frozenset({STATE_ACTIVE, STATE_PAUSED})

# Upper bound (in minutes) for the forward scan that computes ``next_run_at``.
# 366 days covers leap years; a schedule that matches nothing within this
# horizon stores ``next_run_at = NULL`` rather than scanning unboundedly.
_NEXT_RUN_SCAN_MINUTES = 366 * 24 * 60


class SchedulerError(Exception):
    """Raised when a Scheduler operation cannot be completed.

    Carries a human-readable message — for example, an unknown task id or an
    invalid lifecycle state.
    """


# A clock returns the current time as a timezone-aware UTC datetime.
Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    """Default clock: the current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class Scheduler:
    """Persists Scheduled_Tasks and starts due Workflow_Runs on each tick.

    Thread-safe: a single re-entrant lock serializes create/pause/resume and the
    trigger loop so a tick cannot interleave with a state change against stale
    rows.

    :param state: the shared :class:`DatabaseBackend`.
    :param executor: a :class:`~core.dag_executor.DagExecutor` (duck-typed: any
        object exposing ``start_run(definition_id) -> run_id``) used to start a
        Workflow_Run when a task is due.
    :param clock: an injectable callable returning the current UTC time; defaults
        to the wall clock. Injecting a fixed clock makes :meth:`tick`
        deterministic under test.
    :param parser: an injectable :class:`CronParser`; defaults to a new instance.
    """

    def __init__(
        self,
        state: DatabaseBackend,
        executor: Any,
        *,
        clock: Clock | None = None,
        parser: CronParser | None = None,
    ) -> None:
        if state is None:
            raise ValueError("a DatabaseBackend is required")
        if executor is None:
            raise ValueError("a DagExecutor is required")
        if not hasattr(executor, "start_run"):
            raise TypeError("executor must expose start_run(definition_id)")
        self._state = state
        self._executor = executor
        self._clock: Clock = clock or _utc_now
        self._parser = parser or CronParser()
        self._lock = threading.RLock()

    # -- creation (Requirements 14.1, 14.5) --------------------------------

    def create(
        self,
        definition_id: str,
        cron_expression: str,
        *,
        state: str = STATE_ACTIVE,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        """Persist a Workflow_Definition↔schedule association.

        Validates ``cron_expression`` with the Cron_Parser before persisting:
        an invalid expression is rejected with the descriptive
        :class:`~core.cron_parser.CronParseError` and **no** row is written
        (Requirement 14.5). The task is stored in either an ``active`` or a
        ``paused`` state (Requirement 14.1); an active task also records its next
        run time. Returns the persisted task as a dict.
        """
        if not definition_id:
            raise ValueError("definition_id is required to create a scheduled task")
        if state not in _VALID_STATES:
            raise SchedulerError(
                f"invalid scheduled task state {state!r}; expected one of "
                f"{sorted(_VALID_STATES)}"
            )

        # Validate via the Cron_Parser FIRST so an invalid expression is rejected
        # before anything is persisted (Req 14.5). CronParseError carries a
        # descriptive message and propagates to the caller.
        schedule = self._parser.parse(cron_expression)

        new_id = task_id or str(uuid.uuid4())
        ts = now_iso()
        next_run_at = (
            self._next_run_at(schedule, self._clock())
            if state == STATE_ACTIVE
            else None
        )

        with self._lock:
            self._state.execute(
                "INSERT INTO scheduled_tasks "
                "(id, definition_id, cron_expression, state, next_run_at, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    new_id,
                    definition_id,
                    cron_expression,
                    state,
                    next_run_at,
                    ts,
                    ts,
                ),
            )
        LOGGER.debug(
            "created scheduled task %s for definition %s (state=%s)",
            new_id,
            definition_id,
            state,
        )
        return self.get(new_id)  # type: ignore[return-value]

    # -- pause / resume (Requirement 14.3) ---------------------------------

    def pause(self, task_id: str) -> dict[str, Any]:
        """Pause a Scheduled_Task so it stops triggering new runs.

        A paused task is skipped by :meth:`tick` until it is resumed
        (Requirement 14.3). Its ``next_run_at`` is cleared so the paused state is
        unambiguous. Raises :class:`SchedulerError` for an unknown task.
        """
        return self._set_state(task_id, STATE_PAUSED)

    def resume(self, task_id: str) -> dict[str, Any]:
        """Resume a paused Scheduled_Task so it can trigger runs again.

        Recomputes ``next_run_at`` from the current time. Raises
        :class:`SchedulerError` for an unknown task.
        """
        return self._set_state(task_id, STATE_ACTIVE)

    def _set_state(self, task_id: str, new_state: str) -> dict[str, Any]:
        if not task_id:
            raise ValueError("task_id is required")
        with self._lock:
            task = self.get(task_id)
            if task is None:
                raise SchedulerError(f"unknown scheduled task `{task_id}`")
            next_run_at = (
                self._next_run_at(
                    self._parser.parse(task["cron_expression"]), self._clock()
                )
                if new_state == STATE_ACTIVE
                else None
            )
            self._state.execute(
                "UPDATE scheduled_tasks "
                "SET state = ?, next_run_at = ?, updated_at = ? WHERE id = ?",
                (new_state, next_run_at, now_iso(), task_id),
            )
        return self.get(task_id)  # type: ignore[return-value]

    # -- trigger loop (Requirements 14.2, 14.3) ----------------------------

    def tick(self, now: datetime | None = None) -> list[str]:
        """Start a Workflow_Run for every active task due at ``now``.

        Evaluates each ``active`` task against its parsed
        :class:`~core.cron_parser.Schedule`; a task is *due* when ``now``'s
        minute, hour, day-of-month, month, and day-of-week all fall within the
        schedule's value sets. Each due task starts a Workflow_Run via
        ``DagExecutor.start_run`` (Requirement 14.2). Paused tasks are never
        considered, so they never trigger (Requirement 14.3).

        ``now`` defaults to the injected clock. Returns the ids of the runs that
        were started, in task-id order.
        """
        moment = now if now is not None else self._clock()
        started: list[str] = []

        with self._lock:
            rows = self._state.fetch_all(
                "SELECT id, definition_id, cron_expression FROM scheduled_tasks "
                "WHERE state = ? ORDER BY id ASC",
                (STATE_ACTIVE,),
            )
            for row in rows:
                schedule = self._parser.parse(row["cron_expression"])
                if not self._matches(schedule, moment):
                    continue
                run_id = self._executor.start_run(row["definition_id"])
                started.append(run_id)
                # Advance the recorded next run time past this match.
                next_run_at = self._next_run_at(
                    schedule, moment + timedelta(minutes=1)
                )
                self._state.execute(
                    "UPDATE scheduled_tasks "
                    "SET next_run_at = ?, updated_at = ? WHERE id = ?",
                    (next_run_at, now_iso(), row["id"]),
                )
                LOGGER.debug(
                    "scheduled task %s due at %s -> started run %s",
                    row["id"],
                    moment.isoformat(),
                    run_id,
                )
        return started

    # -- queries -----------------------------------------------------------

    def get(self, task_id: str) -> dict[str, Any] | None:
        """Return a single Scheduled_Task by id, or ``None`` if absent."""
        if not task_id:
            return None
        row = self._state.fetch_one(
            "SELECT id, definition_id, cron_expression, state, next_run_at, "
            "created_at, updated_at FROM scheduled_tasks WHERE id = ?",
            (task_id,),
        )
        return dict(row) if row is not None else None

    def list_tasks(
        self, *, definition_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Return persisted Scheduled_Tasks, optionally filtered by definition.

        Ordered by creation time (then id) for a stable, reviewable listing.
        """
        if definition_id is None:
            rows = self._state.fetch_all(
                "SELECT id, definition_id, cron_expression, state, next_run_at, "
                "created_at, updated_at FROM scheduled_tasks "
                "ORDER BY created_at ASC, id ASC"
            )
        else:
            rows = self._state.fetch_all(
                "SELECT id, definition_id, cron_expression, state, next_run_at, "
                "created_at, updated_at FROM scheduled_tasks "
                "WHERE definition_id = ? ORDER BY created_at ASC, id ASC",
                (definition_id,),
            )
        return [dict(row) for row in rows]

    # -- schedule matching -------------------------------------------------

    @staticmethod
    def _matches(schedule: Schedule, moment: datetime) -> bool:
        """Return ``True`` when ``moment`` falls within the schedule's sets.

        Uses the canonical 5-field cron AND semantics: minute, hour,
        day-of-month, month, and day-of-week must all match. Cron numbers the
        days of the week with Sunday as 0, so the Python weekday (Monday as 0)
        is converted accordingly.
        """
        cron_dow = (moment.weekday() + 1) % 7  # Mon=0..Sun=6 -> Sun=0..Sat=6
        return (
            moment.minute in schedule.minute
            and moment.hour in schedule.hour
            and moment.day in schedule.day_of_month
            and moment.month in schedule.month
            and cron_dow in schedule.day_of_week
        )

    def _next_run_at(self, schedule: Schedule, after: datetime) -> str | None:
        """Return the next minute at/after ``after`` that matches, as ISO text.

        Scans minute by minute up to a bounded horizon and returns ``None`` if no
        match falls within it. Used only for the informational ``next_run_at``
        column; the trigger decision in :meth:`tick` is made by :meth:`_matches`.
        """
        # Truncate to whole minutes; cron resolution is one minute.
        moment = after.replace(second=0, microsecond=0)
        for _ in range(_NEXT_RUN_SCAN_MINUTES):
            if self._matches(schedule, moment):
                return moment.strftime("%Y-%m-%dT%H:%M:%SZ")
            moment += timedelta(minutes=1)
        return None
