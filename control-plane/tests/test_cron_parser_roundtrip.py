# Feature: orchestration-engine-completion, Property 35: Cron_Parser round-trip
"""Property-based test for the Cron_Parser round-trip property.

Validates: Requirements 14.4

Property 35 (Cron_Parser round-trip): for every valid cron expression ``e``,
``parse(format(parse(e)))`` equals ``parse(e)``. Parsing produces a canonical
:class:`Schedule` (an expanded set of values per field), so formatting and
re-parsing must yield a Schedule equal to the original parse.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from core.cron_parser import CronParser


# Bounds for each positional cron field. The day-of-week field additionally
# accepts 7 as an alias for Sunday (0), so its inclusive upper bound is 7.
_FIELD_BOUNDS: tuple[tuple[int, int], ...] = (
    (0, 59),  # minute
    (0, 23),  # hour
    (1, 31),  # day_of_month
    (1, 12),  # month
    (0, 7),  # day_of_week (7 is an accepted alias for 0)
)


def _field_components(min_value: int, max_value: int) -> st.SearchStrategy[str]:
    """Strategy for a single cron field component within ``[min, max]``.

    Exercises every supported component form: ``*``, single values, ranges,
    lists (composed at the field level), and steps (``*/n``, ``a-b/n``,
    ``a/n``). Only valid components are generated so parsing never raises.
    """
    wildcard = st.just("*")

    single = st.integers(min_value=min_value, max_value=max_value).map(str)

    # A valid range a-b requires a <= b.
    ranges = st.tuples(
        st.integers(min_value=min_value, max_value=max_value),
        st.integers(min_value=min_value, max_value=max_value),
    ).map(lambda lo_hi: f"{min(lo_hi)}-{max(lo_hi)}")

    # Cron steps must be positive integers (1 or greater).
    steps = st.integers(min_value=1, max_value=max(max_value, 1))

    wildcard_step = steps.map(lambda n: f"*/{n}")

    range_step = st.tuples(
        st.integers(min_value=min_value, max_value=max_value),
        st.integers(min_value=min_value, max_value=max_value),
        steps,
    ).map(lambda t: f"{min(t[0], t[1])}-{max(t[0], t[1])}/{t[2]}")

    value_step = st.tuples(
        st.integers(min_value=min_value, max_value=max_value),
        steps,
    ).map(lambda t: f"{t[0]}/{t[1]}")

    return st.one_of(
        wildcard,
        single,
        ranges,
        wildcard_step,
        range_step,
        value_step,
    )


def _field(min_value: int, max_value: int) -> st.SearchStrategy[str]:
    """Strategy for a full cron field: a comma-separated list of components."""
    return st.lists(
        _field_components(min_value, max_value),
        min_size=1,
        max_size=4,
    ).map(",".join)


@st.composite
def cron_expressions(draw: st.DrawFn) -> str:
    """Generate a valid 5-field cron expression across all fields.

    Each field independently exercises ``*``, single values, ranges, lists,
    and steps within that field's bounds, yielding only well-formed
    expressions that :meth:`CronParser.parse` accepts.
    """
    fields = [draw(_field(low, high)) for low, high in _FIELD_BOUNDS]
    return " ".join(fields)


@settings(max_examples=200)
@given(expression=cron_expressions())
def test_cron_parser_round_trip(expression: str) -> None:
    """parse(format(parse(e))) == parse(e) for all valid cron expressions."""
    once = CronParser.parse(expression)
    twice = CronParser.parse(CronParser.format(once))
    assert twice == once
