"""Question-answering module with optional document retrieval context."""

from __future__ import annotations

import dspy


class QASignature(dspy.Signature):
    """Answer a question using the provided context documents."""

    documents: str = dspy.InputField(desc="Concatenated context documents or passages")
    question: str = dspy.InputField(desc="The question to answer")
    answer: str = dspy.OutputField(desc="Concise factual answer grounded in the documents")
    confidence: str = dspy.OutputField(
        desc="Confidence level: high | medium | low, with one-sentence justification"
    )


class QuestionAnswerer(dspy.Module):
    """
    RAG-style QA. Pass retrieved documents as a single string.

    Usage::

        qa = QuestionAnswerer()
        result = qa(documents="Python 3.11 added tomllib...", question="When was tomllib added?")
        print(result.answer, result.confidence)
    """

    def __init__(self) -> None:
        super().__init__()
        self.predict = dspy.ChainOfThought(QASignature)

    def forward(self, documents: str, question: str) -> dspy.Prediction:
        return self.predict(documents=documents, question=question)
