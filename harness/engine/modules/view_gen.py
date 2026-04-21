"""ViewGenerator DSPy module — generates React TSX view stubs.

Given a natural-language description the LM produces:
  - react_code       — complete TSX file content (no markdown fences)
  - component_name   — safe PascalCase identifier used as the directory name
  - view_spec        — LM's own concise spec / rationale for the generated view
"""

from __future__ import annotations

import dspy


class ViewGeneratorSignature(dspy.Signature):
    """You are a senior React/TypeScript developer embedded in the VLoop Harness.

    VLoop uses Material UI v5 with a dark theme (background.default="#0f0f13").
    All custom view stubs live under react/src/components/generated/{component_name}/.

    When asked to create a React view:
      1. Output a SINGLE, self-contained TSX file in react_code.
         • Use MUI components (Box, Typography, Paper, …).
         • Import only from "react", "@mui/material", and "@mui/icons-material".
         • DO NOT import from relative paths, node built-ins, or unknown packages.
         • DO NOT use eval, require('child_process'), or process.env.
         • Export one default React function component whose name matches
           component_name exactly.
         • Do NOT wrap the code in markdown fences — raw TSX only.
      2. component_name must be PascalCase, letters/digits only, 2–64 chars.
      3. view_spec is a one-paragraph plain-English description of what the view
         does and what props / data it expects.
    """

    ui_description: str = dspy.InputField(
        desc="Natural-language description of the UI to build"
    )
    available_components: str = dspy.InputField(
        desc="JSON array of existing DSPy components [{id, name, description}] for context"
    )
    spec: str = dspy.InputField(
        desc="Optional additional technical spec or constraints (may be empty)"
    )
    react_code: str = dspy.OutputField(
        desc="Complete TSX source — no markdown fences, no relative imports"
    )
    component_name: str = dspy.OutputField(
        desc="PascalCase component name used as the file/directory identifier"
    )
    view_spec: str = dspy.OutputField(
        desc="One-paragraph plain-English spec describing the view's purpose and props"
    )


class ViewGenerator(dspy.Module):
    def __init__(self) -> None:
        self.cot = dspy.ChainOfThought(ViewGeneratorSignature)

    def forward(
        self,
        ui_description: str,
        available_components: str = "[]",
        spec: str = "",
    ) -> dspy.Prediction:
        return self.cot(
            ui_description=ui_description,
            available_components=available_components,
            spec=spec,
        )
