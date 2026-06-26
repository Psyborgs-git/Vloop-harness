"""Custom DSPy agent definitions and invocation runtime (shim).

All functionality has been split into focused sub-modules.
This module re-exports the public API for backward compatibility.
"""

from core.agent_orchestrator import AgentOrchestrator
from core.agent_templates import TEMPLATES, AgentTemplate

__all__ = ["AgentOrchestrator", "AgentTemplate", "TEMPLATES"]
