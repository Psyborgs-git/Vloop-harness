"""DSPy modules — reusable AI building blocks for harness components."""

from harness.engine.modules.code_gen import CodeGenerator
from harness.engine.modules.qa import QuestionAnswerer
from harness.engine.modules.reasoning import ChainOfThoughtReasoner
from harness.engine.modules.summarise import Summariser

__all__ = [
    "ChainOfThoughtReasoner",
    "CodeGenerator",
    "QuestionAnswerer",
    "Summariser",
]
