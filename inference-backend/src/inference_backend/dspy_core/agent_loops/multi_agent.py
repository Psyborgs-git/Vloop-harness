"""MultiAgent loop — orchestrator + specialist role-based agents."""
from __future__ import annotations

import dspy
from typing import Any


class OrchestratorSignature(dspy.Signature):
    """You are an orchestrator. Assign the task to the most appropriate specialist."""
    task: str = dspy.InputField()
    specialists: str = dspy.InputField(desc="Comma-separated list of available specialist roles")
    assigned_to: str = dspy.OutputField(desc="Name of the specialist to handle this task")
    sub_task: str = dspy.OutputField(desc="Refined task description for the specialist")


class SpecialistSignature(dspy.Signature):
    """You are a specialist. Complete your assigned sub-task."""
    role: str = dspy.InputField(desc="Your specialist role")
    sub_task: str = dspy.InputField(desc="The specific task assigned to you")
    answer: str = dspy.OutputField(desc="Your specialist answer")


class SynthesiserSignature(dspy.Signature):
    """Synthesise specialist answers into a final cohesive answer."""
    original_task: str = dspy.InputField()
    specialist_answers: str = dspy.InputField(desc="All specialist answers, formatted as role: answer")
    final_answer: str = dspy.OutputField(desc="Synthesised final answer")


DEFAULT_SPECIALISTS = ["researcher", "analyst", "writer", "coder"]


class MultiAgentLoop(dspy.Module):
    def __init__(self, specialists: list[str] | None = None) -> None:
        super().__init__()
        self.specialists = specialists or DEFAULT_SPECIALISTS
        self.orchestrator = dspy.ChainOfThought(OrchestratorSignature)
        self.specialist = dspy.ChainOfThought(SpecialistSignature)
        self.synthesiser = dspy.ChainOfThought(SynthesiserSignature)

    def forward(self, task: str) -> dspy.Prediction:
        orch = self.orchestrator(
            task=task,
            specialists=", ".join(self.specialists),
        )

        # Run the assigned specialist (in a real system, all relevant ones)
        role = orch.assigned_to.strip()
        if role not in self.specialists:
            role = self.specialists[0]

        spec_pred = self.specialist(role=role, sub_task=orch.sub_task)
        specialist_answers = f"{role}: {spec_pred.answer}"

        synth = self.synthesiser(
            original_task=task,
            specialist_answers=specialist_answers,
        )
        return dspy.Prediction(
            answer=synth.final_answer,
            orchestration={"assigned_to": role, "sub_task": orch.sub_task},
        )


def run(task: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = config or {}
    loop = MultiAgentLoop(specialists=cfg.get("specialists"))
    pred = loop(task=task)
    return {
        "answer": pred.answer,
        "orchestration": getattr(pred, "orchestration", {}),
        "loop": "multi_agent",
    }
