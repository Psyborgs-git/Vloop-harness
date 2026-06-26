"""Agent template definitions — curated DSPy agent blueprints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class AgentTemplate:
    id: str
    name: str
    description: str
    instructions: str
    input_fields: list[dict[str, Any]]
    output_mode: str
    output_field_name: str
    output_schema: dict[str, Any] | None
    reasoning_mode: str
    temperature: float
    max_tokens: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "instructions": self.instructions,
            "inputFields": self.input_fields,
            "outputMode": self.output_mode,
            "outputFieldName": self.output_field_name,
            "outputSchema": self.output_schema,
            "reasoningMode": self.reasoning_mode,
            "temperature": self.temperature,
            "maxTokens": self.max_tokens,
        }


TEMPLATES = [
    AgentTemplate(
        id="summarizer",
        name="Release-note summarizer",
        description="Turn long updates into concise, stakeholder-ready bullets.",
        instructions="You are a concise product operations agent. Summarize the supplied material into clear bullets, surface risks, and keep the tone practical.",
        input_fields=[
            {
                "name": "source_text",
                "label": "Source text",
                "description": "The raw material to summarize.",
                "required": True,
            },
            {
                "name": "audience",
                "label": "Audience",
                "description": "Who the summary is for.",
                "required": False,
            },
        ],
        output_mode="text",
        output_field_name="response",
        output_schema=None,
        reasoning_mode="chain_of_thought",
        temperature=0.2,
        max_tokens=700,
    ),
    AgentTemplate(
        id="json_briefer",
        name="Structured research briefer",
        description="Return a machine-readable brief from arbitrary input.",
        instructions="You are a research synthesis agent. Extract the main theme, the critical constraints, and the next actions from the supplied material.",
        input_fields=[
            {
                "name": "topic",
                "label": "Topic",
                "description": "The topic or request to analyze.",
                "required": True,
            },
            {
                "name": "context",
                "label": "Context",
                "description": "Any extra context, notes, or source material.",
                "required": False,
            },
        ],
        output_mode="json",
        output_field_name="response",
        output_schema={
            "theme": "string",
            "constraints": ["string"],
            "next_actions": ["string"],
        },
        reasoning_mode="chain_of_thought",
        temperature=0.1,
        max_tokens=900,
    ),
]
