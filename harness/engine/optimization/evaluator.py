"""Evaluator — run evaluations on DSPy modules with metrics and dataset management."""

from __future__ import annotations

import asyncio
import functools
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import dspy


MetricFunction = Callable[[dspy.Example, dspy.Prediction, Any | None], float]


@dataclass
class EvalResult:
    """Result of evaluating a module."""

    module_name: str
    dataset_name: str
    score: float
    total_examples: int
    passed_examples: int
    failed_examples: int
    details: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "module_name": self.module_name,
            "dataset_name": self.dataset_name,
            "score": self.score,
            "total_examples": self.total_examples,
            "passed_examples": self.passed_examples,
            "failed_examples": self.failed_examples,
            "duration_ms": self.duration_ms,
            "details": self.details,
        }


class Evaluator:
    """Evaluates DSPy modules against datasets with configurable metrics."""

    def __init__(self) -> None:
        self._metrics: dict[str, MetricFunction] = {}
        self._register_default_metrics()

    # ── Metrics ───────────────────────────────────────────────────────────────

    def _register_default_metrics(self) -> None:
        self.register_metric("exact_match", self._exact_match)
        self.register_metric("contains", self._contains)
        self.register_metric("length_ratio", self._length_ratio)

    def register_metric(self, name: str, fn: MetricFunction) -> None:
        self._metrics[name] = fn

    def get_metric(self, name: str) -> MetricFunction:
        if name not in self._metrics:
            raise KeyError(f"Unknown metric: {name!r}")
        return self._metrics[name]

    # ── Evaluation ──────────────────────────────────────────────────────────

    async def evaluate(
        self,
        module: dspy.Module,
        dataset: list[dspy.Example],
        metric_name: str = "exact_match",
        output_key: str = "answer",
    ) -> EvalResult:
        """Evaluate *module* against *dataset* using the named metric."""
        metric = self.get_metric(metric_name)
        t0 = time.time()

        loop = asyncio.get_running_loop()
        details: list[dict[str, Any]] = []
        passed = 0

        for example in dataset:
            try:
                fn = functools.partial(module, **{k: example[k] for k in example.inputs()})
                prediction = await loop.run_in_executor(None, fn)
                score = metric(example, prediction)
                is_pass = score >= 0.5
                if is_pass:
                    passed += 1

                details.append({
                    "inputs": {k: example[k] for k in example.inputs()},
                    "expected": example.get(output_key, "")
                    if hasattr(example, "__getitem__")
                    else getattr(example, output_key, ""),
                    "predicted": str(getattr(prediction, output_key, prediction)),
                    "score": score,
                    "passed": is_pass,
                })
            except Exception as exc:
                details.append({
                    "inputs": {k: example[k] for k in example.inputs()},
                    "error": str(exc),
                    "score": 0.0,
                    "passed": False,
                })

        duration_ms = int((time.time() - t0) * 1000)
        total = len(dataset)
        avg_score = sum(d["score"] for d in details) / total if total else 0.0

        return EvalResult(
            module_name=module.__class__.__name__,
            dataset_name="eval_dataset",
            score=avg_score,
            total_examples=total,
            passed_examples=passed,
            failed_examples=total - passed,
            details=details,
            duration_ms=duration_ms,
        )

    # ── Batch evaluation ────────────────────────────────────────────────────

    async def evaluate_components(
        self,
        components: list[tuple[str, dspy.Module]],
        dataset: list[dspy.Example],
        metric_name: str = "exact_match",
    ) -> list[EvalResult]:
        """Evaluate multiple components and return ranked results."""
        results = []
        for name, module in components:
            result = await self.evaluate(module, dataset, metric_name)
            results.append(result)
        results.sort(key=lambda r: r.score, reverse=True)
        return results

    # ── Default metrics ─────────────────────────────────────────────────────

    @staticmethod
    def _exact_match(example: dspy.Example, prediction: dspy.Prediction, trace: Any = None) -> float:
        expected = str(example.get("answer", example.get("output", "")))
        predicted = str(getattr(prediction, "answer", getattr(prediction, "output", prediction)))
        return 1.0 if expected.strip().lower() == predicted.strip().lower() else 0.0

    @staticmethod
    def _contains(example: dspy.Example, prediction: dspy.Prediction, trace: Any = None) -> float:
        expected = str(example.get("answer", example.get("output", "")))
        predicted = str(getattr(prediction, "answer", getattr(prediction, "output", prediction)))
        return 1.0 if expected.strip().lower() in predicted.strip().lower() else 0.0

    @staticmethod
    def _length_ratio(example: dspy.Example, prediction: dspy.Prediction, trace: Any = None) -> float:
        expected = str(example.get("answer", example.get("output", "")))
        predicted = str(getattr(prediction, "answer", getattr(prediction, "output", prediction)))
        exp_len = max(1, len(expected))
        pred_len = max(1, len(predicted))
        ratio = min(exp_len, pred_len) / max(exp_len, pred_len)
        return ratio
