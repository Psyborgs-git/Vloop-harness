"""Optimization framework — DSPy teleprompters, evaluation, feedback, self-improvement."""

from harness.engine.optimization.evaluator import EvalResult, Evaluator, MetricFunction
from harness.engine.optimization.feedback import FeedbackCollector, FeedbackEntry
from harness.engine.optimization.optimizer import DSpyOptimizer, OptimizerConfig
from harness.engine.optimization.self_improve import ImprovementConfig, SelfImprovementLoop

__all__ = [
    "DSpyOptimizer",
    "OptimizerConfig",
    "Evaluator",
    "MetricFunction",
    "EvalResult",
    "FeedbackCollector",
    "FeedbackEntry",
    "SelfImprovementLoop",
    "ImprovementConfig",
]
