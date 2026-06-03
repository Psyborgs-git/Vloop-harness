"""SelfImprovementLoop — orchestrates generate → compile → evaluate → optimize → iterate.

Given a user instruction (e.g., "build a sentiment analyzer"), the harness:
  1. Generates a DSPy component from the spec.
  2. Creates a synthetic eval dataset.
  3. Evaluates the baseline.
  4. Optimizes using a teleprompter.
  5. Re-evaluates and compares.
  6. Iterates until the score threshold is met or max iterations reached.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import dspy

from harness.engine.optimization.evaluator import EvalResult, Evaluator
from harness.engine.optimization.feedback import FeedbackCollector
from harness.engine.optimization.optimizer import DSpyOptimizer, OptimizerConfig


@dataclass
class ImprovementConfig:
    """Configuration for the self-improvement loop."""

    target_score: float = 0.85
    max_iterations: int = 3
    examples_per_iteration: int = 5
    metric_name: str = "contains"
    optimizer_config: OptimizerConfig = field(default_factory=OptimizerConfig)


@dataclass
class ImprovementResult:
    """Result of a self-improvement run."""

    component_name: str
    baseline_score: float
    final_score: float
    iterations: int
    improved: bool
    module: dspy.Module | None = None
    eval_results: list[EvalResult] = field(default_factory=list)
    dataset: list[dspy.Example] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_name": self.component_name,
            "baseline_score": self.baseline_score,
            "final_score": self.final_score,
            "iterations": self.iterations,
            "improved": self.improved,
            "eval_results": [r.to_dict() for r in self.eval_results],
        }


class SelfImprovementLoop:
    """Self-improving harness that bootstraps and optimizes DSPy components."""

    def __init__(
        self,
        optimizer: DSpyOptimizer | None = None,
        evaluator: Evaluator | None = None,
        feedback: FeedbackCollector | None = None,
        config: ImprovementConfig | None = None,
    ) -> None:
        self.optimizer = optimizer or DSpyOptimizer()
        self.evaluator = evaluator or Evaluator()
        self.feedback = feedback or FeedbackCollector()
        self.config = config or ImprovementConfig()

    # ── Main loop ─────────────────────────────────────────────────────────────

    async def improve(
        self,
        module: dspy.Module,
        module_name: str,
        trainset: list[dspy.Example] | None = None,
        testset: list[dspy.Example] | None = None,
    ) -> ImprovementResult:
        """Run the full self-improvement loop on a module."""
        cfg = self.config

        # Build datasets if not provided
        if trainset is None:
            trainset = await self._synthesize_trainset(module, module_name)
        if testset is None:
            testset = trainset  # Use same set if no testset provided

        # Baseline eval
        baseline_result = await self.evaluator.evaluate(
            module, testset, metric_name=cfg.metric_name
        )
        baseline_score = baseline_result.score

        if baseline_score >= cfg.target_score:
            return ImprovementResult(
                component_name=module_name,
                baseline_score=baseline_score,
                final_score=baseline_score,
                iterations=0,
                improved=False,
                module=module,
                eval_results=[baseline_result],
                dataset=testset,
            )

        current_module = module
        eval_results = [baseline_result]
        final_score = baseline_score

        for _iteration in range(1, cfg.max_iterations + 1):
            # Optimize
            metric = self.evaluator.get_metric(cfg.metric_name)
            try:
                current_module = self.optimizer.compile(
                    current_module, trainset=trainset, metric=metric
                )
            except Exception:
                # Optimization failed — break
                break

            # Re-evaluate
            eval_result = await self.evaluator.evaluate(
                current_module, testset, metric_name=cfg.metric_name
            )
            eval_results.append(eval_result)
            final_score = eval_result.score

            if final_score >= cfg.target_score:
                break

        improved = final_score > baseline_score

        return ImprovementResult(
            component_name=module_name,
            baseline_score=baseline_score,
            final_score=final_score,
            iterations=len(eval_results) - 1,
            improved=improved,
            module=current_module,
            eval_results=eval_results,
            dataset=testset,
        )

    async def improve_from_feedback(
        self,
        module: dspy.Module,
        component_id: str,
        module_name: str,
    ) -> ImprovementResult:
        """Re-optimize a module using collected positive feedback as training data."""
        examples = self.feedback.to_examples(component_id)
        if len(examples) < 3:
            return ImprovementResult(
                component_name=module_name,
                baseline_score=0.0,
                final_score=0.0,
                iterations=0,
                improved=False,
                module=module,
            )

        trainset = [
            dspy.Example(**ex["inputs"]).with_inputs(*ex["inputs"].keys())
            for ex in examples
        ]
        return await self.improve(module, module_name, trainset=trainset)

    # ── Dataset synthesis ─────────────────────────────────────────────────────

    async def _synthesize_trainset(
        self,
        module: dspy.Module,
        module_name: str,
    ) -> list[dspy.Example]:
        """Generate synthetic training examples for the module."""
        # Use the module's signature to understand inputs/outputs
        # This is a heuristic fallback; in production you'd use the chat module
        # or a dedicated synthetic data generator.
        sig = getattr(module, "signature", None)
        input_fields = []
        output_fields = []
        if sig:
            for name, field in getattr(sig, "fields", {}).items():
                if getattr(field, "input", False):
                    input_fields.append(name)
                else:
                    output_fields.append(name)

        # Create minimal synthetic examples
        examples: list[dspy.Example] = []
        for i in range(self.config.examples_per_iteration):
            ex = dspy.Example(
                question=f"Synthetic example {i + 1} for {module_name}",
                answer=f"Synthetic answer {i + 1}",
            ).with_inputs("question")
            examples.append(ex)
        return examples

    # ── Utility ─────────────────────────────────────────────────────────────

    async def generate_and_improve(
        self,
        spec: str,
        generator: Any,
    ) -> ImprovementResult:
        """Generate a component from spec and immediately improve it."""
        # generator should be a DSPy module that outputs component_code
        loop = asyncio.get_running_loop()
        fn = functools.partial(generator, description=spec)
        prediction = await loop.run_in_executor(None, fn)
        code = getattr(prediction, "python_code", "")
        component_name = getattr(prediction, "component_name", "GeneratedComponent")

        # Compile the generated code into a module
        namespace: dict[str, Any] = {"dspy": dspy}
        try:
            exec(compile(code, f"<{component_name}>", "exec"), namespace)
        except Exception as exc:
            raise RuntimeError(f"Generated code failed to compile: {exc}") from exc

        module_class = None
        for obj in namespace.values():
            if isinstance(obj, type) and issubclass(obj, dspy.Module) and obj is not dspy.Module:
                module_class = obj
                break

        if module_class is None:
            raise RuntimeError("No dspy.Module subclass found in generated code")

        module = module_class()
        return await self.improve(module, component_name)
