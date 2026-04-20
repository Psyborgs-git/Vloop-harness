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
    Components can be chained into Pipelines.

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
         pipeline_config with keys: name, description, steps (array of
         {component_id, input_map}).  Leave empty string if not relevant.

      4. Be concise, technically accurate, and friendly.
    """

    history: str = dspy.InputField(desc="Prior conversation messages (User/Assistant turns)")
    user_message: str = dspy.InputField(desc="The user's latest message")
    available_components: str = dspy.InputField(
        desc="JSON array of available DSPy components [{id, name, description}]"
    )
    available_pipelines: str = dspy.InputField(
        desc="JSON array of available pipelines [{id, name, description}]"
    )
    response: str = dspy.OutputField(desc="Your helpful response shown to the user")
    component_code: str = dspy.OutputField(
        desc="Complete Python DSPy component code if creating one, empty string otherwise"
    )
    pipeline_config: str = dspy.OutputField(
        desc="JSON pipeline configuration if creating a pipeline, empty string otherwise"
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
    ) -> dspy.Prediction:
        return self.cot(
            history=history,
            user_message=user_message,
            available_components=available_components,
            available_pipelines=available_pipelines,
        )
