"""ReAct agent loop — Reasoning + Acting with tool calls."""
from __future__ import annotations

import dspy
from typing import Any

from ...tools.registry import ToolRegistry


class ReActLoop(dspy.Module):
    def __init__(self, tools: list, max_steps: int = 10) -> None:
        super().__init__()
        self.react = dspy.ReAct(
            dspy.Signature(
                "task -> answer",
                "Given the task, reason and act using the available tools to produce an answer.",
            ),
            tools=tools,
            max_iters=max_steps,
        )

    def forward(self, task: str) -> dspy.Prediction:
        return self.react(task=task)


def run(task: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = config or {}
    registry = ToolRegistry()
    tools = registry.get_all_callables()
    loop = ReActLoop(tools=tools, max_steps=cfg.get("max_steps", 10))
    pred = loop(task=task)
    return {
        "answer": pred.answer,
        "loop": "react",
    }
