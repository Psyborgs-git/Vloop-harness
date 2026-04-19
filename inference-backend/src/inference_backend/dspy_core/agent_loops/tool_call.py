"""ToolCall agent loop — structured tool-use with typed signatures."""
from __future__ import annotations

import dspy
from typing import Any

from ...tools.registry import ToolRegistry


class ToolCallSignature(dspy.Signature):
    """Select and call the best tool to answer the task."""
    task: str = dspy.InputField(desc="The task requiring a tool call")
    tool_name: str = dspy.OutputField(desc="Name of the tool to call")
    tool_input: str = dspy.OutputField(desc="JSON-serialised input for the tool")
    reasoning: str = dspy.OutputField(desc="Why this tool was selected")


class ToolCallLoop(dspy.Module):
    def __init__(self, max_steps: int = 5) -> None:
        super().__init__()
        self.max_steps = max_steps
        self.selector = dspy.ChainOfThought(ToolCallSignature)

    def forward(self, task: str) -> dspy.Prediction:
        import json
        registry = ToolRegistry()
        steps = []
        last_result = None

        for _ in range(self.max_steps):
            pred = self.selector(task=task)
            tool = registry.get(pred.tool_name)
            if tool is None:
                break
            try:
                inputs = json.loads(pred.tool_input)
                result = tool(**inputs)
            except Exception as exc:
                result = f"Tool error: {exc}"
            steps.append({
                "tool": pred.tool_name,
                "input": pred.tool_input,
                "output": str(result),
            })
            last_result = result
            if "done" in str(result).lower() or "answer" in pred.reasoning.lower():
                break

        return dspy.Prediction(answer=str(last_result), steps=steps)


def run(task: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = config or {}
    loop = ToolCallLoop(max_steps=cfg.get("max_steps", 5))
    pred = loop(task=task)
    return {
        "answer": pred.answer,
        "steps": pred.steps,
        "loop": "tool_call",
    }
