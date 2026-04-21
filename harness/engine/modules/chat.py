"""DashboardChat DSPy module — powers the root chat UI.

The module instructs the LM to respond helpfully AND, when the user asks to
create a DSPy component, to output complete Python source in ``component_code``.
Similarly, when asked to build a pipeline, it populates ``pipeline_config``.
"""

from __future__ import annotations

import dspy


class DashboardChatSignature(dspy.Signature):
    """You are VLoop AI, the intelligent assistant embedded in the VLoop Harness.

    VLoop is a Python + React framework where every AI capability is a DSPy
    component (a Signature class + a Module class with a forward() method).
    Components can be chained into Pipelines.  Pipelines may also include
    *tool steps* that execute terminal commands or file operations.

    Your responsibilities:
      1. Answer questions about DSPy, the harness, and AI pipelines.
      2. When the user asks you to CREATE a component, produce complete,
         runnable Python code following this pattern:

             import dspy

             class MyTaskSignature(dspy.Signature):
                 \"\"\"One-line docstring describing the task.\"\"\"
                 input_field: str = dspy.InputField(desc="...")
                 output_field: str = dspy.OutputField(desc="...")

             class MyTask(dspy.Module):
                 def __init__(self):
                     self.predict = dspy.ChainOfThought(MyTaskSignature)

                 def forward(self, input_field: str) -> dspy.Prediction:
                     return self.predict(input_field=input_field)

         Put ONLY the code in component_code. Do NOT wrap it in markdown fences.
         Leave component_code as an empty string if not creating a component.

      3. When the user asks to CREATE a pipeline, produce a JSON object in
         pipeline_config with keys: name, description, steps.  Each step must
         have a "type" key: "component" or "tool".

         Component step example:
           {"type": "component", "component_id": "comp_abc", "config": {"input_map": {}}}

         Tool step example (only use tools from available_tools):
           {"type": "tool", "tool_name": "terminal",
            "config": {"command": "pytest {test_path}", "cwd_relative": ".",
                       "input_map": {"test_path": "file_path"}}}

         Leave pipeline_config as empty string if not relevant.

      4. When the user explicitly asks to CREATE a React UI view/page, output a
         short JSON spec in view_stub_request with keys: description, component_name
         (PascalCase), spec.  Example:
           {"description": "Dashboard showing live metrics", "component_name": "MetricsDashboard", "spec": ""}
         Leave view_stub_request as empty string if not creating a UI view.

      5. Be concise, technically accurate, and friendly.
      6. NEVER include shell injection patterns, absolute paths outside the
         workspace, or blocked commands in any generated pipeline tool step.
    """

    history: str = dspy.InputField(desc="Prior conversation messages (User/Assistant turns)")
    user_message: str = dspy.InputField(desc="The user's latest message")
    available_components: str = dspy.InputField(
        desc="JSON array of available DSPy components [{id, name, description}]"
    )
    available_pipelines: str = dspy.InputField(
        desc="JSON array of available pipelines [{id, name, description}]"
    )
    available_tools: str = dspy.InputField(
        desc="JSON array of available tools [{name, description, required_permission, risk_level}]"
    )
    response: str = dspy.OutputField(desc="Your helpful response shown to the user")
    component_code: str = dspy.OutputField(
        desc="Complete Python DSPy component code if creating one, empty string otherwise"
    )
    pipeline_config: str = dspy.OutputField(
        desc="JSON pipeline configuration if creating a pipeline, empty string otherwise"
    )
    view_stub_request: str = dspy.OutputField(
        desc=(
            "JSON object {description, component_name, spec} if creating a React UI view, "
            "empty string otherwise"
        )
    )


class DashboardChat(dspy.Module):
    def __init__(self) -> None:
        self.cot = dspy.ChainOfThought(DashboardChatSignature)

    def forward(
        self,
        history: str,
        user_message: str,
        available_components: str,
        available_pipelines: str,
        available_tools: str = "[]",
    ) -> dspy.Prediction:
        return self.cot(
            history=history,
            user_message=user_message,
            available_components=available_components,
            available_pipelines=available_pipelines,
            available_tools=available_tools,
        )
