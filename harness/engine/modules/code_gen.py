"""Code generation module — produces runnable code from a natural-language spec."""

from __future__ import annotations

import dspy


class CodeGenSignature(dspy.Signature):
    """Generate correct, idiomatic code given a specification."""

    language: str = dspy.InputField(desc="Target programming language (e.g. Python, TypeScript)")
    specification: str = dspy.InputField(desc="Natural language description of what to implement")
    context: str = dspy.InputField(desc="Existing code or constraints to respect", default="")
    code: str = dspy.OutputField(desc="Complete, runnable implementation")
    explanation: str = dspy.OutputField(desc="Brief explanation of the implementation")


class CodeGenerator(dspy.Module):
    """
    Generate code from a spec using chain-of-thought.

    Usage::

        gen = CodeGenerator()
        result = gen(language="Python", specification="A function that reverses a string")
        print(result.code)
    """

    def __init__(self) -> None:
        super().__init__()
        self.generate = dspy.ChainOfThought(CodeGenSignature)

    def forward(self, language: str, specification: str, context: str = "") -> dspy.Prediction:
        return self.generate(language=language, specification=specification, context=context)
