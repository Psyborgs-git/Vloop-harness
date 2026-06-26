"""Route handlers for the VLoop control plane — system, providers, agents, invocations, settings, workloads.

Import these modules at application startup so route registrations run.
"""

# Side-effect imports — each module calls register() at import time.
import cp.handlers.agents  # noqa: F401
import cp.handlers.invocations  # noqa: F401
import cp.handlers.providers  # noqa: F401
import cp.handlers.settings  # noqa: F401
import cp.handlers.system  # noqa: F401
import cp.handlers.workloads  # noqa: F401
from cp.handlers.router import register, route

__all__ = ["register", "route"]
