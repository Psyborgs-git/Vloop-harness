"""Shared orchestration dataclasses and state enums.

These are the in-memory model types exchanged between the orchestration
subsystems (Planner, DAG_Executor, Inference_Gateway, Tool_Registry, ...).
They hold no behavior beyond lightweight helpers; persistence is handled
through ``DatabaseBackend`` and ``core.helpers`` JSON helpers.

Security invariant: ``GrantContext`` references a Kernel secret grant by
id/session only. Raw secret values are NEVER read into Control_Plane state
(Requirements 6.5, 16.4, 18.4).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class RunState(str, Enum):
    """Lifecycle states of a Workflow_Run.

    Values match the ``workflow_runs.state`` column in ``core/database.py``.
    """

    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    BUDGET_EXCEEDED = "budget_exceeded"

    @property
    def is_terminal(self) -> bool:
        """True when no further transition is possible for this run."""
        return self in _TERMINAL_RUN_STATES


class StepState(str, Enum):
    """Lifecycle states of a Workflow_Step.

    Values match the ``workflow_steps.state`` column in ``core/database.py``.
    """

    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"

    @property
    def is_terminal(self) -> bool:
        """True when no further transition is possible for this step."""
        return self in _TERMINAL_STEP_STATES


_TERMINAL_RUN_STATES: frozenset[RunState] = frozenset(
    {
        RunState.COMPLETED,
        RunState.FAILED,
        RunState.CANCELLED,
        RunState.REJECTED,
        RunState.BUDGET_EXCEEDED,
    }
)

_TERMINAL_STEP_STATES: frozenset[StepState] = frozenset(
    {
        StepState.COMPLETED,
        StepState.FAILED,
        StepState.CANCELLED,
        StepState.SKIPPED,
    }
)


@dataclass(slots=True)
class GrantContext:
    """A reference to a Kernel secret grant.

    Carries only the grant id and the granted session reference; it never
    holds a raw secret value (Requirements 6.5, 16.4, 18.4).
    """

    grant_id: str
    session_ref: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Budget:
    """A spend/usage allowance for a scope, plus cumulative usage.

    ``max_tokens``/``max_cost`` of ``None`` mean "unbounded" for that
    dimension (Requirement 7.1).
    """

    max_tokens: int | None = None
    max_cost: float | None = None
    used_tokens: int = 0
    used_cost: float = 0.0

    def remaining_tokens(self) -> int | None:
        if self.max_tokens is None:
            return None
        return self.max_tokens - self.used_tokens

    def remaining_cost(self) -> float | None:
        if self.max_cost is None:
            return None
        return self.max_cost - self.used_cost

    def would_exceed(self, tokens: int = 0, cost: float = 0.0) -> bool:
        """True if charging ``tokens``/``cost`` would breach either limit."""
        if self.max_tokens is not None and self.used_tokens + tokens > self.max_tokens:
            return True
        if self.max_cost is not None and self.used_cost + cost > self.max_cost:
            return True
        return False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ModelRequest:
    """A single model call request handed to the Inference_Gateway."""

    messages: list[dict[str, Any]]
    model_hint: str | None = None
    cache_key: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RoutingPolicy:
    """Policy used by the Provider_Router to order provider candidates."""

    preference: str = "cost"  # "cost" | "speed" | "quality"
    fallback_order: list[str] = field(default_factory=list)  # provider ids
    max_retries: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RunScope:
    """Identifies the Workflow_Run a model call/tool invocation belongs to."""

    run_id: str
    definition_id: str
    budget: Budget | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ToolSpec:
    """A named, schema-described function an agent can call.

    ``mutating`` marks tools that perform filesystem mutation or command
    execution; such tools must be routed through a Kernel-managed Sandbox
    (Requirement 9.5).
    """

    name: str
    description: str
    toolset: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    mutating: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ToolsetSpec:
    """A named, enable/disable-able group of Tools."""

    id: str
    name: str
    tools: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ToolScope:
    """Agent-level and run-level enable/disable maps for toolsets.

    Maps are keyed by toolset name to an enabled boolean. An agent-level
    disable takes precedence over a run-level enable (Requirements 9.2, 9.3).
    """

    agent_enabled: dict[str, bool] = field(default_factory=dict)
    run_enabled: dict[str, bool] = field(default_factory=dict)

    def is_toolset_enabled(self, toolset: str) -> bool:
        """Resolve enablement with agent-level disable taking precedence.

        A toolset is enabled only when it is not disabled at the agent level
        and is enabled at either the agent or run level. Toolsets absent from
        both maps are treated as disabled.
        """
        # Agent-level disable always wins (Requirement 9.3).
        if self.agent_enabled.get(toolset) is False:
            return False
        if self.agent_enabled.get(toolset) is True:
            return True
        return self.run_enabled.get(toolset, False)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ToolResult:
    """Outcome of a single Tool invocation, returned by the Tool_Registry.

    ``denied`` marks an invocation the Tool_Registry refused because the tool's
    toolset was not enabled in the caller's scope (Requirement 9.4).
    ``sandboxed`` marks an invocation that performed filesystem mutation or
    command execution and was therefore routed through a Kernel-managed Sandbox
    (Requirement 9.5).
    """

    tool_name: str
    ok: bool
    output: Any | None = None
    error_message: str | None = None
    denied: bool = False
    sandboxed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class StepResult:
    """Outcome of a single Workflow_Step, reported back to the DAG_Executor."""

    step_id: str
    state: StepState
    output: dict[str, Any] | None = None
    error_message: str | None = None
    token_usage: int | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        # Serialize the enum to its string value for JSON storage.
        data["state"] = self.state.value
        return data
