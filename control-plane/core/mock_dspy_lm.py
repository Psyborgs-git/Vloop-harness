"""Mock DSPy LM — deterministic local provider for smoke testing."""

from __future__ import annotations

import importlib
import json
import re
from types import SimpleNamespace
from typing import Any

_OUTPUT_FIELD_PATTERN = re.compile(
    r"Return the final answer in the `([a-zA-Z][a-zA-Z0-9_]*)` field\."
)
_DSPY_FIELD_MARKER_PATTERN = re.compile(
    r"\[\[\s*##\s*([a-zA-Z][a-zA-Z0-9_]*)\s*##\s*\]\]"
)
_JSON_GUIDANCE_PATTERN = re.compile(r"JSON shape guidance:\s*(\{.*?\})", re.S)


def _extract_mock_output_field_name(prompt_text: str) -> str:
    match = _OUTPUT_FIELD_PATTERN.search(prompt_text)
    if match:
        return match.group(1)

    markers = [
        marker
        for marker in _DSPY_FIELD_MARKER_PATTERN.findall(prompt_text)
        if marker not in {"request", "reasoning"}
    ]
    if markers:
        return markers[-1]

    return "response"


def _extract_mock_json_shape(prompt_text: str) -> dict[str, Any] | None:
    match = _JSON_GUIDANCE_PATTERN.search(prompt_text)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _materialize_mock_json_shape(shape: Any, *, field_name: str) -> Any:
    if isinstance(shape, dict):
        if not shape:
            return {field_name: f"Mock {field_name}"}
        return {
            str(key): _materialize_mock_json_shape(value, field_name=str(key))
            for key, value in shape.items()
        }
    if isinstance(shape, list):
        if not shape:
            return [f"Mock {field_name} item"]
        return [_materialize_mock_json_shape(shape[0], field_name=field_name)]
    if isinstance(shape, str):
        normalized = shape.strip().lower()
        if normalized in {"number", "float", "int", "integer"}:
            return 1
        if normalized in {"boolean", "bool"}:
            return True
        if normalized in {"array", "list"}:
            return [f"Mock {field_name} item"]
        if normalized in {"object", "json"}:
            return {field_name: f"Mock {field_name}"}
        return f"Mock {field_name}"
    if isinstance(shape, bool):
        return shape
    if isinstance(shape, (int, float)):
        return shape
    return f"Mock {field_name}"


def create_mock_dspy_lm(model: str) -> Any:
    """Build a deterministic mock DSPy LM that echoes inputs.

    Parses the prompt for JSON shape guidance to produce structured
    responses or plain-text echoes for text-mode agents.
    """
    try:
        dspy = importlib.import_module("dspy")
        base_class = dspy.BaseLM
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "DSPy is required for the mock LM provider because agent execution is DSPy-driven."
        ) from exc

    class MockDSPyLM(base_class):
        def __init__(self, model_name: str) -> None:
            super().__init__(
                model=model_name,
                model_type="chat",
                temperature=0.0,
                max_tokens=512,
                cache=False,
            )

        def forward(
            self,
            prompt: str | None = None,
            messages: list[dict[str, Any]] | None = None,
            **kwargs: Any,
        ):
            transcript = messages or []
            user_message = transcript[-1]["content"] if transcript else (prompt or "")
            user_message = str(user_message)
            output_field_name = _extract_mock_output_field_name(user_message)
            reasoning_text = (
                "Mock provider produced a deterministic local response for smoke tests."
            )
            response_text = (
                "Mock provider reply from VLoop. This proves the DSPy pipeline is working locally. "
                f"Input excerpt: {user_message[:220]}"
            )
            json_shape = _extract_mock_json_shape(user_message)
            if json_shape is not None:
                output_value = _materialize_mock_json_shape(
                    json_shape,
                    field_name=output_field_name,
                )
            else:
                output_value = response_text
            payload = json.dumps(
                {
                    "reasoning": reasoning_text,
                    output_field_name: output_value,
                },
                ensure_ascii=False,
            )
            message = SimpleNamespace(
                content=payload,
                reasoning_content=reasoning_text,
            )
            choice = SimpleNamespace(message=message)
            return SimpleNamespace(
                choices=[choice],
                usage={
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                },
                _hidden_params={},
                model=self.model,
            )

    return MockDSPyLM(model)
