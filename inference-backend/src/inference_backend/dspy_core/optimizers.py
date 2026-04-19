"""DSPy optimiser hooks (BootstrapFewShot, MIPROv2)."""
from __future__ import annotations

import dspy
from dspy.teleprompt import BootstrapFewShot

try:
    from dspy.teleprompt import MIPROv2
    _has_mipro = True
except ImportError:
    _has_mipro = False


def bootstrap_optimise(
    program: dspy.Module,
    metric,
    trainset: list,
    max_demos: int = 3,
) -> dspy.Module:
    """Run BootstrapFewShot optimisation."""
    optimizer = BootstrapFewShot(metric=metric, max_labeled_demos=max_demos)
    return optimizer.compile(program, trainset=trainset)


def mipro_optimise(
    program: dspy.Module,
    metric,
    trainset: list,
    **kwargs,
) -> dspy.Module:
    """Run MIPROv2 optimisation if available."""
    if not _has_mipro:
        raise ImportError("MIPROv2 not available in this DSPy version")
    optimizer = MIPROv2(metric=metric, **kwargs)
    return optimizer.compile(program, trainset=trainset)
