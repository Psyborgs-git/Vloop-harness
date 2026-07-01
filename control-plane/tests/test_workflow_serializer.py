"""Unit tests for core.workflow_serializer (canonical serialize/deserialize)."""

from __future__ import annotations

import json

import pytest

from core.workflow_serializer import SerializationError, WorkflowSerializer


@pytest.fixture
def serializer() -> WorkflowSerializer:
    return WorkflowSerializer()


def _sample_definition() -> dict:
    return {
        "version": 1,
        "name": "Nightly report",
        "objective": "Summarize yesterday's activity",
        "inputs": {"date": "2024-01-01"},
        "steps": [
            {"id": "fetch", "type": "tool", "config": {"source": "db"}, "dependsOn": []},
            {
                "id": "summarize",
                "type": "agent",
                "config": {"agent": "writer"},
                "dependsOn": ["fetch"],
            },
        ],
        "policies": {"max_retries": 2},
    }


def test_serialize_emits_sorted_keys(serializer: WorkflowSerializer):
    out = serializer.serialize(_sample_definition())
    # Top-level keys appear in sorted order in the emitted text.
    top_keys = list(json.loads(out).keys())
    assert top_keys == sorted(top_keys)
    # Nested step keys are also sorted.
    first_step_keys = list(json.loads(out)["steps"][0].keys())
    assert first_step_keys == sorted(first_step_keys)


def test_serialize_normalizes_to_canonical_shape(serializer: WorkflowSerializer):
    out = json.loads(serializer.serialize(_sample_definition()))
    assert set(out.keys()) == {
        "version",
        "name",
        "objective",
        "inputs",
        "steps",
        "policies",
    }
    assert set(out["steps"][0].keys()) == {"id", "type", "config", "dependsOn"}


def test_serialize_drops_unknown_keys_and_defaults_missing(serializer: WorkflowSerializer):
    out = json.loads(serializer.serialize({"name": "x", "extra": "ignored"}))
    assert "extra" not in out
    assert out["version"] == 1
    assert out["objective"] == ""
    assert out["inputs"] == {}
    assert out["steps"] == []
    assert out["policies"] == {}


def test_deserialize_round_trip_example(serializer: WorkflowSerializer):
    d = _sample_definition()
    once = serializer.serialize(d)
    twice = serializer.serialize(serializer.deserialize(once))
    assert once == twice


def test_serialize_is_byte_stable_across_key_ordering(serializer: WorkflowSerializer):
    a = {"name": "x", "objective": "o", "version": 1}
    b = {"version": 1, "objective": "o", "name": "x"}
    assert serializer.serialize(a) == serializer.serialize(b)


def test_deserialize_rejects_malformed_json(serializer: WorkflowSerializer):
    with pytest.raises(SerializationError):
        serializer.deserialize("{not valid json")


def test_deserialize_rejects_empty_input(serializer: WorkflowSerializer):
    with pytest.raises(SerializationError):
        serializer.deserialize("   ")


def test_deserialize_rejects_non_object_json(serializer: WorkflowSerializer):
    with pytest.raises(SerializationError):
        serializer.deserialize("[1, 2, 3]")


def test_deserialize_rejects_bad_steps_type(serializer: WorkflowSerializer):
    with pytest.raises(SerializationError):
        serializer.deserialize(json.dumps({"steps": "not-a-list"}))


def test_deserialize_rejects_non_string_input(serializer: WorkflowSerializer):
    with pytest.raises(SerializationError):
        serializer.deserialize(123)  # type: ignore[arg-type]
