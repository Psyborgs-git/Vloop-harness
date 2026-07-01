# Feature: orchestration-engine-completion, Property 5: Workflow_Serializer rejects malformed input gracefully
"""Property-based test for graceful malformed-input handling in the serializer.

Property 5: Workflow_Serializer rejects malformed input gracefully.
Validates: Requirements 2.4

For *any* malformed serialized input, ``WorkflowSerializer.deserialize`` either
succeeds (returns a canonical Workflow_Definition dict) or raises the documented,
descriptive :class:`SerializationError`. No other exception type is allowed to
escape — an unhandled exception (``json.JSONDecodeError``, ``TypeError``,
``AttributeError``, ``RecursionError``, etc.) would violate Requirement 2.4.

The ``serialized_definitions()`` strategy intentionally emits corrupted/garbage
forms: arbitrary text and bytes, broken JSON fragments, well-formed JSON of the
wrong top-level type, and partially-canonical objects whose fields have been
corrupted to the wrong types.
"""

from __future__ import annotations

import json
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from core.workflow_serializer import SerializationError, WorkflowSerializer


# --- Building blocks for garbage / corrupted input ---------------------------

# Arbitrary JSON-ish values used both as standalone garbage and as corrupted
# field values inside otherwise-canonical-looking objects.
_json_scalars = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(),
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(),
)

_json_values: st.SearchStrategy[Any] = st.recursive(
    _json_scalars,
    lambda children: st.one_of(
        st.lists(children, max_size=4),
        st.dictionaries(st.text(max_size=8), children, max_size=4),
    ),
    max_leaves=15,
)


@st.composite
def _corrupted_canonical_objects(draw: st.DrawFn) -> str:
    """JSON objects shaped like definitions but with wrong-typed fields/steps."""
    obj: dict[str, Any] = {
        "version": draw(_json_values),
        "name": draw(_json_values),
        "objective": draw(_json_values),
        "inputs": draw(_json_values),
        "steps": draw(_json_values),
        "policies": draw(_json_values),
    }
    return json.dumps(obj)


@st.composite
def _corrupted_step_lists(draw: st.DrawFn) -> str:
    """Objects with a 'steps' list whose members are garbage of mixed types."""
    steps = draw(st.lists(_json_values, max_size=5))
    return json.dumps({"name": draw(st.text(max_size=8)), "steps": steps})


def _well_formed_json_wrong_type() -> st.SearchStrategy[str]:
    """Valid JSON whose top-level value is not an object (array/number/etc.)."""
    return st.one_of(
        st.lists(_json_values, max_size=5),
        st.integers(),
        st.floats(allow_nan=False, allow_infinity=False),
        st.text(),
        st.booleans(),
        st.none(),
    ).map(json.dumps)


def serialized_definitions() -> st.SearchStrategy[Any]:
    """Emit corrupted/garbage serialized forms (strings and bytes).

    Covers: free-form text, raw bytes, broken JSON fragments, valid JSON of the
    wrong type, and partially-canonical objects with corrupted fields/steps.
    """
    return st.one_of(
        st.text(),  # arbitrary text, incl. empty / whitespace / broken JSON
        st.binary(),  # bytes are not valid input and must be rejected gracefully
        _well_formed_json_wrong_type(),
        _corrupted_canonical_objects(),
        _corrupted_step_lists(),
    )


@settings(max_examples=300)
@given(serialized=serialized_definitions())
def test_deserialize_rejects_malformed_input_gracefully(serialized: Any) -> None:
    serializer = WorkflowSerializer()
    try:
        result = serializer.deserialize(serialized)
    except SerializationError:
        # Documented, descriptive error — the acceptable failure mode (Req 2.4).
        return
    # If it did not raise, it must have produced a canonical definition dict.
    assert isinstance(result, dict)
    assert set(result.keys()) == {
        "version",
        "name",
        "objective",
        "inputs",
        "steps",
        "policies",
    }
