"""Chain-of-Thought agent loop."""
from __future__ import annotations

import dspy
from typing import Any, Callable


class CoTSignature(dspy.Signature):
    """Think step-by-step and answer the question."""
    task: str = dspy.InputField(desc="The task to complete")
    reasoning: str = dspy.OutputField(desc="Step-by-step reasoning (scratchpad)")
    answer: str = dspy.OutputField(desc="Final answer")


class ChainOfThoughtLoop(dspy.Module):
    def __init__(self) -> None:
        super().__init__()
        self.cot = dspy.ChainOfThought(CoTSignature)

    def forward(self, task: str) -> dspy.Prediction:
        return self.cot(task=task)


def run(
    task: str,
    config: dict[str, Any] | None = None,
    step_callback: Callable[[int, str, str], None] | None = None,
) -> dict[str, Any]:
    loop = ChainOfThoughtLoop()
    pred = loop(task=task)
    reasoning = getattr(pred, "reasoning", "")
    if step_callback and reasoning:
        step_callback(0, "reasoning", reasoning)
    return {
        "answer": pred.answer,
        "reasoning": reasoning,
        "loop": "chain_of_thought",
    }
