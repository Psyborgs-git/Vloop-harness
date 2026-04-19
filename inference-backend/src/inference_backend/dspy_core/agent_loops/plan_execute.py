"""PlanAndExecute agent loop — decompose task then execute steps."""
from __future__ import annotations

import dspy
from typing import Any


class PlanSignature(dspy.Signature):
    """Decompose the task into ordered steps."""
    task: str = dspy.InputField()
    plan: str = dspy.OutputField(desc="Numbered list of steps to execute")


class ExecuteStepSignature(dspy.Signature):
    """Execute a single step of the plan."""
    task: str = dspy.InputField(desc="Original task")
    plan: str = dspy.InputField(desc="Full plan")
    step: str = dspy.InputField(desc="Current step to execute")
    result: str = dspy.OutputField(desc="Result of executing this step")


class PlanAndExecuteLoop(dspy.Module):
    def __init__(self) -> None:
        super().__init__()
        self.planner = dspy.ChainOfThought(PlanSignature)
        self.executor = dspy.ChainOfThought(ExecuteStepSignature)

    def forward(self, task: str) -> dspy.Prediction:
        plan_pred = self.planner(task=task)
        plan = plan_pred.plan

        steps = [s.strip() for s in plan.split("\n") if s.strip()]
        results = []
        for step in steps:
            result_pred = self.executor(task=task, plan=plan, step=step)
            results.append({"step": step, "result": result_pred.result})

        final_answer = "\n".join(f"- {r['step']}: {r['result']}" for r in results)
        return dspy.Prediction(answer=final_answer, plan=plan, steps=results)


def run(task: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    loop = PlanAndExecuteLoop()
    pred = loop(task=task)
    return {
        "answer": pred.answer,
        "plan": pred.plan,
        "steps": pred.steps,
        "loop": "plan_execute",
    }
