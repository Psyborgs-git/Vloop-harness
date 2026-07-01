"""Cron expression parsing and formatting.

Provides :class:`CronParser`, which converts a standard 5-field cron
expression into a :class:`Schedule` and formats a :class:`Schedule` back into
a cron expression. Used by the Scheduler (``core/scheduler.py``) to persist
and trigger Scheduled_Tasks.

A :class:`Schedule` holds, for each field, the *expanded* set of integer
values that match. This canonical representation guarantees the round-trip
property required by Requirement 14.4: for any valid cron expression ``e``,
``parse(format(parse(e))) == parse(e)``. Two cron expressions that match the
same instants — for example ``"7"`` and ``"0"`` in the day-of-week field, or
``"*/1"`` and ``"*"`` — deserialize to equal Schedules.

Supported syntax per field: ``*`` (any), single values, ``a-b`` ranges,
``a,b,c`` lists, and ``*/n`` / ``a-b/n`` / ``a/n`` steps.
"""

from __future__ import annotations

from dataclasses import dataclass


class CronParseError(ValueError):
    """Raised when a cron expression cannot be parsed (Requirement 14.5)."""


@dataclass(frozen=True, slots=True)
class _FieldSpec:
    """Bounds for a single positional cron field."""

    name: str
    min_value: int
    max_value: int


# Standard 5-field cron layout, in positional order.
_FIELD_SPECS: tuple[_FieldSpec, ...] = (
    _FieldSpec("minute", 0, 59),
    _FieldSpec("hour", 0, 23),
    _FieldSpec("day_of_month", 1, 31),
    _FieldSpec("month", 1, 12),
    _FieldSpec("day_of_week", 0, 6),
)

# Position of the day-of-week field, which accepts 7 as an alias for Sunday (0).
_DOW_INDEX = 4
_DOW_ALIAS_VALUE = 7


@dataclass(frozen=True, slots=True)
class Schedule:
    """A parsed cron schedule as an expanded set of values per field.

    Each field holds the full set of integer values that match, so two cron
    expressions describing the same instants compare equal.
    """

    minute: frozenset[int]
    hour: frozenset[int]
    day_of_month: frozenset[int]
    month: frozenset[int]
    day_of_week: frozenset[int]

    def fields(self) -> tuple[frozenset[int], ...]:
        """Return the per-field value sets in positional cron order."""
        return (
            self.minute,
            self.hour,
            self.day_of_month,
            self.month,
            self.day_of_week,
        )


class CronParser:
    """Parses and formats standard 5-field cron expressions."""

    @staticmethod
    def parse(expression: str) -> Schedule:
        """Parse a cron expression into a :class:`Schedule`.

        Raises :class:`CronParseError` for any malformed input rather than
        leaking a low-level exception (Requirement 14.5).
        """
        if not isinstance(expression, str):
            raise CronParseError("cron expression must be a string")

        parts = expression.split()
        if len(parts) != len(_FIELD_SPECS):
            raise CronParseError(
                f"expected {len(_FIELD_SPECS)} fields, got {len(parts)}: "
                f"{expression!r}"
            )

        values = [
            _parse_field(raw, spec, allow_alias=index == _DOW_INDEX)
            for index, (raw, spec) in enumerate(zip(parts, _FIELD_SPECS))
        ]
        return Schedule(*values)

    @staticmethod
    def format(schedule: Schedule) -> str:
        """Format a :class:`Schedule` back into a canonical cron expression."""
        return " ".join(
            _format_field(field, spec)
            for field, spec in zip(schedule.fields(), _FIELD_SPECS)
        )


def _parse_field(raw: str, spec: _FieldSpec, allow_alias: bool) -> frozenset[int]:
    """Expand one comma-separated cron field into its set of values."""
    if raw == "":
        raise CronParseError(f"empty {spec.name} field")

    result: set[int] = set()
    for part in raw.split(","):
        result.update(_parse_part(part, spec, allow_alias))

    if not result:
        raise CronParseError(f"{spec.name} field {raw!r} matched no values")
    return frozenset(result)


def _parse_part(part: str, spec: _FieldSpec, allow_alias: bool) -> set[int]:
    """Expand a single field component (``*``, value, range, or step)."""
    base, step_sep, step_raw = part.partition("/")

    step = 1
    if step_sep:
        step = _parse_int(step_raw, spec, "step")
        if step <= 0:
            raise CronParseError(f"{spec.name} step must be positive: {part!r}")

    # The day-of-week field accepts 7 as an alias for Sunday, so its inclusive
    # upper bound is 7 rather than spec.max_value (6). Mirror _parse_value here.
    upper = _DOW_ALIAS_VALUE if allow_alias else spec.max_value

    if base == "*":
        low, high = spec.min_value, spec.max_value
    elif "-" in base:
        low_raw, _, high_raw = base.partition("-")
        low = _parse_value(low_raw, spec, allow_alias)
        high = _parse_value(high_raw, spec, allow_alias)
        if low > high:
            raise CronParseError(f"{spec.name} range start exceeds end: {part!r}")
    else:
        value = _parse_value(base, spec, allow_alias)
        # "a/step" means "a through the maximum, stepped"; a bare "a" is one value.
        low, high = (value, upper) if step_sep else (value, value)

    return {_normalize(v, allow_alias) for v in range(low, high + 1, step)}


def _parse_value(raw: str, spec: _FieldSpec, allow_alias: bool) -> int:
    """Parse and bounds-check a single field value."""
    value = _parse_int(raw, spec, "value")
    upper = _DOW_ALIAS_VALUE if allow_alias else spec.max_value
    if value < spec.min_value or value > upper:
        raise CronParseError(
            f"{spec.name} value {value} out of range [{spec.min_value}, {upper}]"
        )
    return value


def _parse_int(raw: str, spec: _FieldSpec, kind: str) -> int:
    """Parse a non-negative integer token, rejecting anything else."""
    text = raw.strip()
    if not text or not text.isdigit():
        raise CronParseError(f"invalid {spec.name} {kind}: {raw!r}")
    return int(text)


def _normalize(value: int, allow_alias: bool) -> int:
    """Fold the day-of-week Sunday alias (7) onto its canonical value (0)."""
    if allow_alias and value == _DOW_ALIAS_VALUE:
        return 0
    return value


def _format_field(values: frozenset[int], spec: _FieldSpec) -> str:
    """Render one field as ``*`` when full, otherwise a sorted value list."""
    full_range = set(range(spec.min_value, spec.max_value + 1))
    if set(values) == full_range:
        return "*"
    return ",".join(str(v) for v in sorted(values))
