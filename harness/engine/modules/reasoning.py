"""Chain-of-thought reasoning module."""

from __future__ import annotations

import dspy


class ReasonSignature(dspy.Signature):
    """Reason step-by-step to answer a question or solve a problem."""

    context: str = dspy.InputField(desc="Background context or relevant facts", default="")
    question: str = dspy.InputField(desc="The question or problem to solve")
    reasoning: str = dspy.OutputField(desc="Step-by-step reasoning process")
    answer: str = dspy.OutputField(desc="Final concise answer")


class ChainOfThoughtReasoner(dspy.Module):
    """
    Wraps dspy.ChainOfThought for structured multi-step reasoning.

    Usage::

        reasoner = ChainOfThoughtReasoner()
        result = reasoner(question="What is 2+2?", context="Basic arithmetic")
        print(result.answer)
    """

    def __init__(self) -> None:
        super().__init__()
        self.cot = dspy.ChainOfThought(ReasonSignature)

    def forward(self, question: str, context: str = "") -> dspy.Prediction:
        return self.cot(question=question, context=context)
