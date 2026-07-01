"""Unit tests for core.cron_parser parse/format behavior."""

from __future__ import annotations

import pytest

from core.cron_parser import CronParseError, CronParser, Schedule


def test_all_wildcards_expand_to_full_ranges():
    schedule = CronParser.parse("* * * * *")
    assert schedule.minute == frozenset(range(0, 60))
    assert schedule.hour == frozenset(range(0, 24))
    assert schedule.day_of_month == frozenset(range(1, 32))
    assert schedule.month == frozenset(range(1, 13))
    assert schedule.day_of_week == frozenset(range(0, 7))


def test_single_values():
    schedule = CronParser.parse("30 2 15 6 3")
    assert schedule.minute == frozenset({30})
    assert schedule.hour == frozenset({2})
    assert schedule.day_of_month == frozenset({15})
    assert schedule.month == frozenset({6})
    assert schedule.day_of_week == frozenset({3})


def test_lists_ranges_and_steps():
    schedule = CronParser.parse("0,15,30,45 9-17 * */2 1-5")
    assert schedule.minute == frozenset({0, 15, 30, 45})
    assert schedule.hour == frozenset(range(9, 18))
    assert schedule.month == frozenset({1, 3, 5, 7, 9, 11})
    assert schedule.day_of_week == frozenset({1, 2, 3, 4, 5})


def test_range_with_step():
    schedule = CronParser.parse("0-30/10 * * * *")
    assert schedule.minute == frozenset({0, 10, 20, 30})


def test_value_with_step_runs_to_maximum():
    # "5/10" in the minute field means 5, 15, 25, 35, 45, 55.
    schedule = CronParser.parse("5/10 * * * *")
    assert schedule.minute == frozenset({5, 15, 25, 35, 45, 55})


def test_day_of_week_seven_is_alias_for_sunday():
    seven = CronParser.parse("0 0 * * 7")
    zero = CronParser.parse("0 0 * * 0")
    assert seven == zero
    assert seven.day_of_week == frozenset({0})


def test_format_renders_wildcard_for_full_field():
    schedule = CronParser.parse("0 * * * *")
    assert CronParser.format(schedule) == "0 * * * *"


def test_format_renders_sorted_value_lists():
    schedule = CronParser.parse("*/15 9-11 * * *")
    assert CronParser.format(schedule) == "0,15,30,45 9,10,11 * * *"


@pytest.mark.parametrize(
    "expression",
    [
        "* * * * *",
        "0 0 * * *",
        "*/5 * * * *",
        "0,30 9-17 1,15 */3 1-5",
        "59 23 31 12 6",
        "0 0 * * 7",
        "15-45/10 0-23/4 1-31/5 1-12/2 0-6",
    ],
)
def test_round_trip_examples(expression):
    once = CronParser.parse(expression)
    twice = CronParser.parse(CronParser.format(once))
    assert twice == once


@pytest.mark.parametrize(
    "expression",
    [
        "",  # no fields
        "* * * *",  # too few fields
        "* * * * * *",  # too many fields
        "60 * * * *",  # minute out of range
        "* 24 * * *",  # hour out of range
        "* * 0 * *",  # day-of-month below minimum
        "* * 32 * *",  # day-of-month above maximum
        "* * * 13 *",  # month out of range
        "* * * * 8",  # day-of-week above alias maximum
        "*/0 * * * *",  # zero step
        "5-1 * * * *",  # inverted range
        "a * * * *",  # non-numeric value
        "*/x * * * *",  # non-numeric step
        ", * * * *",  # empty list member
    ],
)
def test_invalid_expressions_raise_descriptive_error(expression):
    with pytest.raises(CronParseError):
        CronParser.parse(expression)


def test_non_string_input_rejected():
    with pytest.raises(CronParseError):
        CronParser.parse(None)  # type: ignore[arg-type]


def test_schedule_equality_ignores_syntactic_form():
    # "*/1" and "*" describe identical instants and must compare equal.
    assert CronParser.parse("*/1 * * * *") == CronParser.parse("* * * * *")
    # Equivalent but differently written ranges/lists.
    assert CronParser.parse("0-2 * * * *") == CronParser.parse("0,1,2 * * * *")
    assert isinstance(CronParser.parse("* * * * *"), Schedule)
