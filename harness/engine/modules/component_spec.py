"""ComponentSpecGenerator DSPy module — generates DSPy component Python source.

Produces structured Python source code for a DSPy component (Signature + Module)
from a natural-language description, with richer spec output than the inline
code_gen path in the chat module.
"""

from __future__ import annotations

import dspy


class ComponentSpecGeneratorSignature(dspy.Signature):
    """You are an expert DSPy framework developer.

    DSPy components consist of two Python classes:
      1. A Signature class — describes inputs/outputs with Field annotations.
      2. A Module class — a dspy.Module subclass with a forward() method.

    Pattern:

        import dspy

        class <Name>Signature(dspy.Signature):
            \"\"\"One-line docstring.\"\"\"
            <input>: str = dspy.InputField(desc="...")
            <output>: str = dspy.OutputField(desc="...")

        class <Name>(dspy.Module):
            def __init__(self):
                self.predict = dspy.ChainOfThought(<Name>Signature)

            def forward(self, <input>: str) -> dspy.Prediction:
                return self.predict(<input>=<input>)

    Rules:
      - Output ONLY raw Python — no markdown fences.
      - Use dspy.ChainOfThought as the predictor unless spec says otherwise.
      - All field types must be str (DSPy requirement for most predictors).
      - component_name must be the Module class name (not the Signature class name).
      - spec_summary is a one-paragraph description of the component's purpose
        and signature contract.
    """

    description: str = dspy.InputField(
        desc="Natural-language description of what the component should do"
    )
    context: str = dspy.InputField(
        desc="Optional additional context or constraints (may be empty)"
    )
    python_code: str = dspy.OutputField(
        desc="Complete Python source — Signature class + Module class, no markdown fences"
    )
    component_name: str = dspy.OutputField(
        desc="The Module class name (PascalCase)"
    )
    spec_summary: str = dspy.OutputField(
        desc="One-paragraph plain-English summary of inputs, outputs, and purpose"
    )


class ComponentSpecGenerator(dspy.Module):
    def __init__(self) -> None:
        self.cot = dspy.ChainOfThought(ComponentSpecGeneratorSignature)

    def forward(
        self,
        description: str,
        context: str = "",
    ) -> dspy.Prediction:
        return self.cot(description=description, context=context)
