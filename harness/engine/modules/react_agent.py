"""ReAct (Reasoning and Acting) Agent module.

Implements the ReAct prompt pattern using DSPy, allowing an agent
to interleve reasoning (Thoughts) with action (Tools) to arrive at a goal.
"""

from __future__ import annotations

import json
from typing import Any

import dspy


class ReActSignature(dspy.Signature):
    """You are an autonomous AI assistant using the ReAct (Reasoning and Acting) pattern.

    Given a task or question, you must follow this exact sequence for each step:
    1. Thought: Reason about what to do next.
    2. Action: Choose exactly one tool to use from the available tools.
    3. Action Input: The parameters to pass to the tool (as a JSON string).

    You will then be provided with an Observation, which contains the result of the tool execution.
    You will repeat the Thought -> Action -> Action Input sequence until you have enough information
    to provide the final answer.

    When you are ready to answer the user or complete the task, use the special tool "finish".
    """

    task: str = dspy.InputField(desc="The task or question to solve.")
    available_tools: str = dspy.InputField(
        desc="JSON array of tools available to you. Format: [{'name': '...', 'description': '...'}]"
    )
    history: str = dspy.InputField(
        desc="History of previous steps (Thoughts, Actions, and Observations)."
    )

    thought: str = dspy.OutputField(desc="Your reasoning about what to do next.")
    action: str = dspy.OutputField(desc="The exact name of the tool to use (or 'finish' if done).")
    action_input: str = dspy.OutputField(
        desc="The JSON string of parameters for the tool (or the final answer string if action is 'finish')."
    )


class ReActAgent(dspy.Module):
    def __init__(self, max_iterations: int = 10) -> None:
        self.cot = dspy.ChainOfThought(ReActSignature)
        self.max_iterations = max_iterations

    def forward(
        self,
        task: str,
        available_tools: str,
        tool_registry: Any,
    ) -> dspy.Prediction:
        """Execute the ReAct loop until 'finish' or max_iterations."""
        history = ""
        iterations = 0
        final_answer = ""

        while iterations < self.max_iterations:
            prediction = self.cot(
                task=task,
                available_tools=available_tools,
                history=history,
            )

            thought = prediction.thought
            action = prediction.action.strip()
            action_input = prediction.action_input.strip()

            # Record thought and action in history
            history += f"\nThought: {thought}\nAction: {action}\nAction Input: {action_input}\n"

            if action.lower() == "finish":
                final_answer = action_input
                break

            # Execute tool
            try:
                # Basic JSON parameter parsing
                try:
                    params = json.loads(action_input)
                except json.JSONDecodeError:
                    # Fallback if the model didn't return proper JSON
                    params = {"input": action_input}

                import asyncio

                try:
                    loop = asyncio.get_running_loop()
                    import nest_asyncio
                    nest_asyncio.apply()
                    tool_result_obj = loop.run_until_complete(
                        tool_registry.execute(
                            tool_name=action, component_id=None, session_id=None, params=params
                        )
                    )
                except RuntimeError:
                    tool_result_obj = asyncio.run(
                        tool_registry.execute(
                            tool_name=action, component_id=None, session_id=None, params=params
                        )
                    )

                if hasattr(tool_result_obj, "to_dict"):
                    observation = json.dumps(tool_result_obj.to_dict())
                else:
                    observation = str(tool_result_obj)

            except Exception as e:
                observation = f"Error executing tool {action}: {e}"

            history += f"Observation: {observation}\n"
            iterations += 1

        if not final_answer:
            final_answer = "Max iterations reached without finishing."

        return dspy.Prediction(answer=final_answer, history=history, iterations=iterations)
