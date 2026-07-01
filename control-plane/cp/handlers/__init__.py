"""Route handlers for the VLoop control plane.

Covers system, providers, agents, invocations, settings, workloads, and the
orchestration-engine surfaces: workflows, schedules, memory, checkpoints,
tools/toolsets, and MCP servers.

Import these modules at application startup so route registrations run. Every
handler module calls ``register()`` at import time, so simply importing the
module (the side-effect imports below) mounts its routes on the shared router.
"""

# Side-effect imports — each module calls register() at import time.
# NOTE: approvals is imported before workflows on purpose — its pending-listing
# route (`/api/v1/workflow-runs/{id}/approvals`) positionally overlaps the
# workflow run-action wildcard, and the router dispatches in registration order.
import cp.handlers.approvals  # noqa: F401
import cp.handlers.agents  # noqa: F401
import cp.handlers.checkpoints  # noqa: F401
import cp.handlers.invocations  # noqa: F401
import cp.handlers.mcp  # noqa: F401
import cp.handlers.memory  # noqa: F401
import cp.handlers.providers  # noqa: F401
import cp.handlers.schedules  # noqa: F401
import cp.handlers.settings  # noqa: F401
import cp.handlers.system  # noqa: F401
import cp.handlers.tools  # noqa: F401
import cp.handlers.workflows  # noqa: F401
import cp.handlers.workloads  # noqa: F401
from cp.handlers.router import register, route

__all__ = ["register", "route"]
