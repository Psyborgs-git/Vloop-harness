"""Property-based test for the Workflow_Serializer round-trip.

# Feature: orchestration-engine-completion, Property 4: Workflow_Serializer round-trip

Property 4 states that for any valid Workflow_Definition ``d``::

    serialize(deserialize(serialize(d))) == serialize(d)

i.e. once a definition has been serialized into the canonical sorted-key JSON
form, deserializing and re-serializing it produces byte-identical output. This
exercises the serialize path (Requirement 2.1), the deserialize path
(Requirement 2.2), and the byte-stable round-trip guarantee (Requirement 2.3).

**Validates: Requirements 2.1, 2.2, 2.3**
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.workflow_serializer import WorkflowSerializer

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# JSON-safe leaf values that survive a json.dumps -> json.loads -> json.dumps
# cycle without changing representation. NaN/Infinity are excluded because they
# are not valid JSON and would not represent a "valid" Workflow_Definition.
_json_scalars = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(10**12), max_value=10**12),
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(max_size=20),
)

# Arbitrary nested JSON-compatible values for free-form dict fields
# (inputs, config, policies). Dict keys are strings, as required by JSON.
_json_values = st.recursive(
    _json_scalars,
    lambda children: st.one_of(
        st.lists(children, max_size=4),
        st.dictionaries(st.text(max_size=8), children, max_size=4),
    ),
    max_leaves=12,
)

# Free-form JSON object used for the inputs/config/policies fields.
_json_objects = st.dictionaries(st.text(max_size=8), _json_values, max_size=5)


def _steps() -> st.SearchStrategy[list[dict]]:
    """Generate a list of canonical-shape Workflow_Steps."""
    step = st.fixed_dictionaries(
        {
            "id": st.text(max_size=12),
            "type": st.sampled_from(["agent", "tool", "approval", "subworkflow"]),
            "config": _json_objects,
            "dependsOn": st.lists(st.text(max_size=12), max_size=4),
        }
    )
    return st.lists(step, max_size=6)


@st.composite
def workflow_definitions(draw: st.DrawFn) -> dict:
    """Generate valid Workflow_Definition dicts of the canonical shape.

    Shape: ``{version, name, objective, inputs, steps[{id, type, config,
    dependsOn}], policies}``.
    """
    return {
        "version": draw(
            st.one_of(st.integers(min_value=1, max_value=1000), st.text(max_size=8))
        ),
        "name": draw(st.text(max_size=40)),
        "objective": draw(st.text(max_size=80)),
        "inputs": draw(_json_objects),
        "steps": draw(_steps()),
        "policies": draw(_json_objects),
    }


# ---------------------------------------------------------------------------
# Property 4: Workflow_Serializer round-trip
# ---------------------------------------------------------------------------


@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
@given(definition=workflow_definitions())
def test_serializer_round_trip(definition: dict) -> None:
    """serialize(deserialize(serialize(d))) == serialize(d) for valid d."""
    serializer = WorkflowSerializer()
    once = serializer.serialize(definition)
    twice = serializer.serialize(serializer.deserialize(once))
    assert once == twice
