"""Property-based test for invalid-schedule rejection (task 25.3).

# Feature: orchestration-engine-completion, Property 36: Invalid schedule expressions are rejected descriptively

Property 36 states that *for any* invalid schedule expression, the Scheduler
rejects the Scheduled_Task and returns a descriptive error. Concretely, for any
expression the Cron_Parser cannot parse, :meth:`Scheduler.create`:

* raises :class:`~core.cron_parser.CronParseError` (a descriptive error whose
  message is non-empty), rather than silently succeeding or leaking a
  low-level exception, and
* persists **no** ``scheduled_tasks`` row — ``list_tasks()`` is unchanged
  (remains empty) after the rejected create.

The test generates a broad space of invalid expressions: wrong field counts
(too few / too many / empty), out-of-range values, non-numeric tokens, and
structurally malformed fields (bad ranges, zero steps, empty list parts). Each
example runs against a fresh temporary SQLite database with a recording
executor that must never be invoked, since a rejected create never starts a
run.

**Validates: Requirements 14.5**
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from core.cron_parser import CronParseError, CronParser
from core.database import SQLiteBackend
from core.scheduler import Scheduler

# ---------------------------------------------------------------------------
# A recording executor that asserts it is never asked to start a run. A
# rejected create must persist nothing and therefore can never trigger a run.
# ---------------------------------------------------------------------------


class _RecordingExecutor:
    def __init__(self) -> None:
        self.started: list[str] = []

    def start_run(self, definition_id: str) -> str:
        self.started.append(definition_id)
        return f"run-{definition_id}"


# ---------------------------------------------------------------------------
# Strategies: generate invalid cron expressions across several failure modes.
# ---------------------------------------------------------------------------

# Tokens that are individually valid in any field, used as filler so only the
# targeted position is responsible for an expression's invalidity.
_VALID_FILLER = st.sampled_from(["*", "0", "1", "5", "*/1"])


@st.composite
def _wrong_field_count(draw: st.DrawFn) -> str:
    """A cron expression with a number of fields other than five."""
    count = draw(st.integers(min_value=0, max_value=9).filter(lambda n: n != 5))
    parts = [draw(_VALID_FILLER) for _ in range(count)]
    return " ".join(parts)


# Per-field inclusive upper bounds (day-of-week tolerates 7 as Sunday alias).
_FIELD_UPPER = (59, 23, 31, 12, 7)
_FIELD_LOWER = (0, 0, 1, 1, 0)


@st.composite
def _out_of_range(draw: st.DrawFn) -> str:
    """Five fields, one carrying a numeric value outside its valid range."""
    position = draw(st.integers(min_value=0, max_value=4))
    upper = _FIELD_UPPER[position]
    lower = _FIELD_LOWER[position]
    # Either above the upper bound or, where possible, below the lower bound.
    if lower > 0 and draw(st.booleans()):
        bad_value = draw(st.integers(min_value=0, max_value=lower - 1))
    else:
        bad_value = draw(st.integers(min_value=upper + 1, max_value=upper + 500))
    parts = [draw(_VALID_FILLER) for _ in range(5)]
    parts[position] = str(bad_value)
    return " ".join(parts)


@st.composite
def _non_numeric(draw: st.DrawFn) -> str:
    """Five fields, one carrying a non-numeric / junk token."""
    junk = draw(
        st.sampled_from(["abc", "x", "@", "!", "foo", "n/a", "--", "1a", "a1"])
        | st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz@#!$%",
            min_size=1,
            max_size=5,
        )
    )
    position = draw(st.integers(min_value=0, max_value=4))
    parts = [draw(_VALID_FILLER) for _ in range(5)]
    parts[position] = junk
    return " ".join(parts)


@st.composite
def _malformed_structure(draw: st.DrawFn) -> str:
    """Five fields, one structurally malformed (bad range, step, list)."""
    malformed = draw(
        st.sampled_from(
            [
                "5-2",  # range start exceeds end
                "*/0",  # step must be positive
                "1-",  # empty range end
                "-5",  # empty range start
                "1,,2",  # empty list element
                "/3",  # empty step base
                "1-2-3",  # too many range parts
                ",",  # only a separator
            ]
        )
    )
    position = draw(st.integers(min_value=0, max_value=4))
    parts = [draw(_VALID_FILLER) for _ in range(5)]
    parts[position] = malformed
    return " ".join(parts)


_INVALID_EXPRESSIONS = st.one_of(
    _wrong_field_count(),
    _out_of_range(),
    _non_numeric(),
    _malformed_structure(),
    # Explicit empties / whitespace-only (zero fields once split).
    st.sampled_from(["", " ", "   ", "\t", "\n"]),
)


# ---------------------------------------------------------------------------
# Property 36
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(expression=_INVALID_EXPRESSIONS)
def test_invalid_schedule_expressions_are_rejected_descriptively(
    expression: str,
) -> None:
    # Restrict the input space to genuinely invalid expressions. Anything the
    # Cron_Parser can parse is out of scope for this property; the strategies
    # above target invalidity, and this guard drops any rare accidental hit.
    parser = CronParser()
    try:
        parser.parse(expression)
    except CronParseError:
        pass
    else:  # pragma: no cover - filtered out, never exercised
        assume(False)

    with tempfile.TemporaryDirectory() as tmp:
        backend = SQLiteBackend(Path(tmp) / "scheduler-prop.db")
        executor = _RecordingExecutor()
        scheduler = Scheduler(backend, executor)

        before = scheduler.list_tasks()
        assert before == []

        try:
            scheduler.create("def-prop", expression)
        except CronParseError as error:
            # The error must be descriptive: a non-empty message.
            assert str(error).strip(), "CronParseError must carry a message"
        else:
            raise AssertionError(
                f"expected CronParseError for invalid expression {expression!r}"
            )

        # No row persisted for the rejected expression (Req 14.5), and no run
        # was ever started.
        assert scheduler.list_tasks() == before == []
        assert executor.started == []
