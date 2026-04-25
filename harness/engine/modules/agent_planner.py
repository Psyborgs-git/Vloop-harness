"""AgentPlanner DSPy module — generates a structured plan for an agent run.

Given a user goal and the current capabilities (components, pipelines, tools),
the planner produces:
  - A step-by-step execution plan in JSON.
  - The initial set of steps to execute.
  - A recommended autonomy mode.
"""

from __future__ import annotations

import dspy


class AgentPlannerSignature(dspy.Signature):
    """You are the VLoop agent planner.

    VLoop is a self-programming harness that can:
      - Create and execute DSPy components and pipelines.
      - Generate React UI views (TSX) that pair with backends.
      - Execute terminal commands, file operations, browser interactions,
        and database queries — all within a policy-gated tool registry.

    Given the user's GOAL, produce a concrete, ordered execution plan as a
    JSON array of steps.  Each step must have these keys:
      - "step_type": one of plan | dspy_call | tool_call | file_write | message
      - "description": human-readable description of what this step does
      - "tool_name": (for tool_call) "terminal" | "filesystem" | "browser" | "database"
      - "params": dict of parameters for this step (tool params, dspy module name, etc.)
      - "requires_confirmation": boolean — true only for destructive/irreversible steps

    Also recommend an autonomy_mode:
      - "observe"          — plan only, no execution
      - "suggest"          — produce plan and artifacts for human review
      - "write_approval"   — write files after human approval of each step
      - "test_approval"    — write + run tests after approval
      - "autonomous"       — full execution with confirmations only for destructive steps

    Be concise. Only include steps that are necessary to achieve the goal.
    Do NOT include steps that use unavailable tools or non-existent components.
    """

    goal: str = dspy.InputField(desc="The user's goal or task description")
    available_components: str = dspy.InputField(
        desc="JSON array of available DSPy components [{id, name, description}]"
    )
    available_pipelines: str = dspy.InputField(
        desc="JSON array of available pipelines [{id, name, description}]"
    )
    available_tools: str = dspy.InputField(
        desc="JSON array of available tools [{name, description, risk_level}]"
    )
    context: str = dspy.InputField(
        desc="Any additional context (current state, prior run output, etc.)"
    )

    plan_json: str = dspy.OutputField(
        desc=(
            "JSON array of step objects. Each step: "
            "{step_type, description, tool_name?, params, requires_confirmation}. "
            "Output ONLY the raw JSON array, no markdown fences."
        )
    )
    autonomy_mode: str = dspy.OutputField(
        desc="Recommended autonomy mode: observe | suggest | write_approval | test_approval | autonomous"
    )
    summary: str = dspy.OutputField(
        desc="One-paragraph plain-text summary of what the plan will accomplish"
    )


class AgentPlanner(dspy.Module):
    def __init__(self) -> None:
        self.cot = dspy.ChainOfThought(AgentPlannerSignature)

    def forward(
        self,
        goal: str,
        available_components: str = "[]",
        available_pipelines: str = "[]",
        available_tools: str = "[]",
        context: str = "",
    ) -> dspy.Prediction:
        return self.cot(
            goal=goal,
            available_components=available_components,
            available_pipelines=available_pipelines,
            available_tools=available_tools,
            context=context,
        )
