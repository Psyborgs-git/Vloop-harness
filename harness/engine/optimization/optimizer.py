"""DSpyOptimizer — wrapper around DSPy teleprompters for prompt optimization."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import dspy


@dataclass
class OptimizerConfig:
    """Configuration for DSPy optimization."""

    teleprompter_type: str = "BootstrapFewShot"  # BootstrapFewShot | MIPROv2
    metric_threshold: float = 0.7
    num_candidates: int = 4
    max_bootstrapped_demos: int = 4
    max_labeled_demos: int = 8
    teacher_settings: dict[str, Any] | None = None
    verbose: bool = True


class DSpyOptimizer:
    """Optimizes DSPy modules using teleprompters.

    Usage::

        optimizer = DSpyOptimizer(config)
        optimized_module = optimizer.compile(module, trainset, metric_fn)
        optimizer.save(optimized_module, path)
    """

    def __init__(self, config: OptimizerConfig | None = None) -> None:
        self.config = config or OptimizerConfig()

    def compile(
        self,
        module: dspy.Module,
        trainset: list[dspy.Example],
        metric: Any,
    ) -> dspy.Module:
        """Run the configured teleprompter to optimize *module*."""
        cfg = self.config

        if cfg.teleprompter_type == "BootstrapFewShot":
            teleprompter = dspy.teleprompt.BootstrapFewShot(
                metric=metric,
                max_bootstrapped_demos=cfg.max_bootstrapped_demos,
                max_labeled_demos=cfg.max_labeled_demos,
            )
            return teleprompter.compile(module, trainset=trainset)

        if cfg.teleprompter_type == "BootstrapFewShotWithRandomSearch":
            teleprompter = dspy.teleprompt.BootstrapFewShotWithRandomSearch(
                metric=metric,
                max_bootstrapped_demos=cfg.max_bootstrapped_demos,
                max_labeled_demos=cfg.max_labeled_demos,
                num_candidate_programs=cfg.num_candidates,
            )
            return teleprompter.compile(module, trainset=trainset)

        # Graceful fallback if MIPROv2 is not available in this DSPy version
        try:
            if cfg.teleprompter_type == "MIPROv2":
                teleprompter = dspy.teleprompt.MIPROv2(
                    metric=metric,
                    num_candidates=cfg.num_candidates,
                    verbose=cfg.verbose,
                )
                return teleprompter.compile(module, trainset=trainset)
        except AttributeError:
            pass

        # Ultimate fallback: BootstrapFewShot
        teleprompter = dspy.teleprompt.BootstrapFewShot(
            metric=metric,
            max_bootstrapped_demos=cfg.max_bootstrapped_demos,
        )
        return teleprompter.compile(module, trainset=trainset)

    def save(self, module: dspy.Module, path: str | Path) -> None:
        """Persist optimized module to disk."""
        if hasattr(module, "save"):
            module.save(path)
        else:
            Path(path).write_text(json.dumps({"_type": "dspy_module", "module": str(module)}), encoding="utf-8")

    def load(self, path: str | Path, module_class: type[dspy.Module]) -> dspy.Module | None:
        """Load optimized module from disk."""
        p = Path(path)
        if not p.exists():
            return None
        instance = module_class()
        if hasattr(instance, "load"):
            instance.load(path)
            return instance
        return None

    def compare_versions(
        self,
        baseline: dspy.Module,
        optimized: dspy.Module,
        testset: list[dspy.Example],
        metric: Any,
    ) -> dict[str, Any]:
        """Compare baseline vs optimized on a test set."""
        import asyncio

        loop = asyncio.new_event_loop()
        try:
            baseline_score = self._score_module(baseline, testset, metric)
            optimized_score = self._score_module(optimized, testset, metric)
        finally:
            loop.close()

        return {
            "baseline_score": baseline_score,
            "optimized_score": optimized_score,
            "improvement": optimized_score - baseline_score,
            "improved": optimized_score > baseline_score,
        }

    @staticmethod
    def _score_module(
        module: dspy.Module,
        testset: list[dspy.Example],
        metric: Any,
    ) -> float:
        """Score a module on a test set."""
        scores = []
        for example in testset:
            prediction = module(**{k: example[k] for k in example.inputs()})
            score = metric(example, prediction)
            scores.append(float(score))
        if not scores:
            return 0.0
        return sum(scores) / len(scores)
