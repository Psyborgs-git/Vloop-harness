"""Chain-of-Thought agent loop."""
from __future__ import annotations

import dspy
from typing import Any


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


def run(task: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    loop = ChainOfThoughtLoop()
    pred = loop(task=task)
    return {
        "answer": pred.answer,
        "reasoning": getattr(pred, "reasoning", ""),
        "loop": "chain_of_thought",
    }
