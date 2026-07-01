"""Workflow_Serializer — canonical serialize/deserialize for Workflow_Definitions.

The Workflow_Serializer persists a Workflow_Definition as canonical JSON with
sorted keys so that re-serialization is byte-stable (Requirement 2.3). The
canonical shape is::

    {
        "version":   <int|str>,
        "name":      <str>,
        "objective": <str>,
        "inputs":    <dict>,
        "steps": [
            {"id": <str>, "type": <str>, "config": <dict>, "dependsOn": [<str>, ...]},
            ...
        ],
        "policies":  <dict>,
    }

Determinism: ``serialize`` first normalizes the definition into the canonical
shape and then emits ``json.dumps(..., sort_keys=True)``. Normalization is
idempotent, so ``serialize(deserialize(serialize(d))) == serialize(d)`` holds
for every valid definition (Requirements 2.1, 2.2, 2.3).

Malformed input handling: ``deserialize`` never lets a raw parser error escape.
Any malformed serialized input raises :class:`SerializationError`, a documented,
descriptive error type, rather than an unhandled exception (Requirement 2.4).

Note on ``core.helpers``: ``helpers.to_json`` does not sort keys, so canonical
serialization uses ``json.dumps(..., sort_keys=True)`` directly; ``deserialize``
uses ``json.loads`` so that malformed JSON can be caught and converted into a
descriptive :class:`SerializationError` (``helpers.from_json`` would silently
return its default for empty input, hiding the malformed case).
"""

from __future__ import annotations

import json
from typing import Any

# Top-level keys of the canonical Workflow_Definition shape, in declared order.
_TOP_LEVEL_KEYS: tuple[str, ...] = (
    "version",
    "name",
    "objective",
    "inputs",
    "steps",
    "policies",
)

# Per-step keys of the canonical shape.
_STEP_KEYS: tuple[str, ...] = ("id", "type", "config", "dependsOn")

_DEFAULT_VERSION = 1


class SerializationError(Exception):
    """Raised when serialized input cannot be deserialized into a definition.

    This is a documented, descriptive error (Requirement 2.4): callers can
    catch it to surface a user-facing message. It replaces any raw parser
    exception (for example ``json.JSONDecodeError``) so the serializer never
    raises an unhandled exception for malformed input.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class WorkflowSerializer:
    """Serializes/deserializes Workflow_Definitions to canonical JSON."""

    def serialize(self, definition: dict[str, Any]) -> str:
        """Serialize a Workflow_Definition into canonical sorted-key JSON.

        The definition is normalized into the canonical shape and emitted with
        sorted keys so the output is byte-stable across equivalent definitions
        (Requirements 2.1, 2.3).
        """
        if not isinstance(definition, dict):
            raise SerializationError(
                f"Workflow_Definition must be an object, got {type(definition).__name__}."
            )
        canonical = _canonicalize(definition)
        return json.dumps(canonical, sort_keys=True, ensure_ascii=False)

    def deserialize(self, serialized: str) -> dict[str, Any]:
        """Deserialize canonical JSON into an in-memory Workflow_Definition.

        Returns a normalized definition equivalent to the one originally
        serialized (Requirement 2.2). Malformed input raises a descriptive
        :class:`SerializationError` rather than an unhandled exception
        (Requirement 2.4).
        """
        if not isinstance(serialized, str):
            raise SerializationError(
                f"Serialized input must be a string, got {type(serialized).__name__}."
            )
        if not serialized.strip():
            raise SerializationError("Serialized input is empty.")
        try:
            parsed = json.loads(serialized)
        except (json.JSONDecodeError, ValueError) as exc:
            raise SerializationError(f"Serialized input is not valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise SerializationError(
                "Serialized Workflow_Definition must be a JSON object, "
                f"got {type(parsed).__name__}."
            )
        return _canonicalize(parsed)


def _canonicalize(definition: dict[str, Any]) -> dict[str, Any]:
    """Normalize a definition into the canonical shape (idempotent).

    Unknown top-level keys are dropped and missing keys are defaulted so that
    re-normalizing an already-canonical definition is a no-op, which is what
    makes the round-trip byte-stable (Requirement 2.3).
    """
    return {
        "version": definition.get("version", _DEFAULT_VERSION),
        "name": _as_str(definition.get("name"), field="name"),
        "objective": _as_str(definition.get("objective"), field="objective"),
        "inputs": _as_dict(definition.get("inputs"), field="inputs"),
        "steps": _canonicalize_steps(definition.get("steps")),
        "policies": _as_dict(definition.get("policies"), field="policies"),
    }


def _canonicalize_steps(steps: Any) -> list[dict[str, Any]]:
    if steps is None:
        return []
    if not isinstance(steps, list):
        raise SerializationError(
            f"Workflow_Definition 'steps' must be a list, got {type(steps).__name__}."
        )
    canonical: list[dict[str, Any]] = []
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            raise SerializationError(
                f"Workflow_Step at index {index} must be an object, "
                f"got {type(step).__name__}."
            )
        canonical.append(
            {
                "id": _as_str(step.get("id"), field=f"steps[{index}].id"),
                "type": _as_str(step.get("type"), field=f"steps[{index}].type"),
                "config": _as_dict(step.get("config"), field=f"steps[{index}].config"),
                "dependsOn": _as_str_list(
                    step.get("dependsOn"), field=f"steps[{index}].dependsOn"
                ),
            }
        )
    return canonical


def _as_str(value: Any, field: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise SerializationError(
            f"Field '{field}' must be a string, got {type(value).__name__}."
        )
    return value


def _as_dict(value: Any, field: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise SerializationError(
            f"Field '{field}' must be an object, got {type(value).__name__}."
        )
    return value


def _as_str_list(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise SerializationError(
            f"Field '{field}' must be a list, got {type(value).__name__}."
        )
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise SerializationError(
                f"Field '{field}[{index}]' must be a string, got {type(item).__name__}."
            )
        result.append(item)
    return result
