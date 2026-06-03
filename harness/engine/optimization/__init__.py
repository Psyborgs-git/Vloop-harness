"""Optimization framework — DSPy teleprompters, evaluation, feedback, self-improvement."""

from harness.engine.optimization.optimizer import DSpyOptimizer, OptimizerConfig
from harness.engine.optimization.evaluator import Evaluator, MetricFunction, EvalResult
from harness.engine.optimization.feedback import FeedbackCollector, FeedbackEntry
from harness.engine.optimization.self_improve import SelfImprovementLoop, ImprovementConfig

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
