"""Summarisation module — condenses long text into a structured summary."""

from __future__ import annotations

import dspy


class SummariseSignature(dspy.Signature):
    """Produce a structured summary of the given text."""

    text: str = dspy.InputField(desc="The text to summarise")
    max_words: int = dspy.InputField(desc="Approximate maximum word count for the summary", default=100)
    summary: str = dspy.OutputField(desc="Concise summary within the word limit")
    key_points: str = dspy.OutputField(desc="Bullet-point list of the most important facts")


class Summariser(dspy.Module):
    """
    Condense long-form text.

    Usage::

        s = Summariser()
        result = s(text="Long article...", max_words=80)
        print(result.summary)
        print(result.key_points)
    """

    def __init__(self) -> None:
        super().__init__()
        self.summarise = dspy.ChainOfThought(SummariseSignature)

    def forward(self, text: str, max_words: int = 100) -> dspy.Prediction:
        return self.summarise(text=text, max_words=max_words)
