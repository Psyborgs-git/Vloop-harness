"""Tool_Registry — tool/toolset catalog and scope gating.

The Tool_Registry is the Control_Plane subsystem that catalogs Tools and the
Toolsets that group them (Requirement 9.1) and enforces which Tools are
available to a given agent or Workflow_Run (Requirements 9.2-9.5).

Gating rules
------------
Enablement is resolved per :class:`~core.orchestration_types.ToolScope`, which
carries both an agent-level and a run-level toolset enable/disable map. An
agent-level *disable* always wins over a run-level *enable* so agent-level
restrictions take precedence (Requirements 9.2, 9.3); the precedence logic
itself lives on :meth:`ToolScope.is_toolset_enabled`.

Denied invocations
------------------
When a Tool whose toolset is not enabled in the current scope is invoked, the
registry denies the call and records the denial in the Workflow_Run event
history via the :class:`~core.event_router.EventRouter` (Requirement 9.4). The
denial is attributed to the run carried by the supplied
:class:`~core.orchestration_types.RunScope`.

Sandbox routing
---------------
A Tool flagged ``mutating`` performs filesystem mutation or command execution
and MUST run inside a Kernel-managed Sandbox (Requirements 9.5, 21.1). Such a
tool is routed through an injected ``sandbox_executor`` callable rather than
being executed on the host. If no sandbox executor is available the invocation
is blocked and :class:`SandboxRoutingBlocked` is raised — there is no host
fallback (Requirement 21.2). Non-mutating tools run through an in-process
handler registered alongside the tool.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from core.event_router import EventRouter, WorkflowEventType
from core.orchestration_types import (
    RunScope,
    ToolResult,
    ToolScope,
    ToolSpec,
    ToolsetSpec,
)

LOGGER = logging.getLogger("vloop.control_plane.tool_registry")

# A non-mutating tool handler: receives the invocation args, returns output.
ToolHandler = Callable[[dict[str, Any]], Any]

# A sandbox executor: receives the tool spec, args, and the enclosing run scope
# (so it can scope the Sandbox to the run's toolset/secret grants), and returns
# the captured output. It MUST execute inside a Kernel-managed Sandbox.
SandboxExecutor = Callable[[ToolSpec, dict[str, Any], "RunScope | None"], Any]


class SandboxRoutingBlocked(RuntimeError):
    """Raised when a mutating tool cannot be routed to a Kernel-managed Sandbox.

    Signals that execution was blocked with no host fallback (Requirements 9.5,
    21.1, 21.2).
    """


class ToolRegistry:
    """Catalogs Tools/Toolsets and enforces scope gating on invocation."""

    def __init__(
        self,
        *,
        event_router: EventRouter | None = None,
        sandbox_executor: SandboxExecutor | None = None,
    ) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._handlers: dict[str, ToolHandler] = {}
        self._toolsets: dict[str, ToolsetSpec] = {}
        # Tools that are catalogued but currently unavailable (for example an
        # MCP server's tools after it becomes unreachable, Requirement 18.3).
        # An unavailable tool stays in the catalog but is never enabled and any
        # invocation is denied.
        self._unavailable: set[str] = set()
        self._event_router = event_router
        self._sandbox_executor = sandbox_executor

    # -- catalog ------------------------------------------------------------

    def register_tool(
        self, tool: ToolSpec, handler: ToolHandler | None = None
    ) -> None:
        """Add (or replace) a Tool in the catalog (Requirement 9.1).

        ``handler`` supplies the in-process implementation for a non-mutating
        tool; mutating tools ignore it and are routed through the sandbox
        executor instead (Requirement 9.5).
        """
        if not tool.name:
            raise ValueError("a tool must have a non-empty name")
        self._tools[tool.name] = tool
        # A (re-)registered tool is available again by default; a prior
        # unavailable mark from an earlier registration must not linger.
        self._unavailable.discard(tool.name)
        if handler is not None:
            self._handlers[tool.name] = handler

    def register_toolset(self, toolset: ToolsetSpec) -> None:
        """Add (or replace) a Toolset grouping in the catalog (Requirement 9.1)."""
        if not toolset.id:
            raise ValueError("a toolset must have a non-empty id")
        self._toolsets[toolset.id] = toolset

    def get_tool(self, tool_name: str) -> ToolSpec | None:
        """Return the catalogued :class:`ToolSpec`, or ``None`` if unknown."""
        return self._tools.get(tool_name)

    def list_tools(self) -> list[ToolSpec]:
        """Return all catalogued tools."""
        return list(self._tools.values())

    def list_toolsets(self) -> list[ToolsetSpec]:
        """Return all catalogued toolsets."""
        return list(self._toolsets.values())

    def tools_in_toolset(self, toolset: str) -> list[ToolSpec]:
        """Return the catalogued tools grouped under ``toolset``.

        Grouping is derived from each tool's ``toolset`` field so it stays
        accurate even when tools are registered before their toolset.
        """
        return [t for t in self._tools.values() if t.toolset == toolset]

    # -- availability -------------------------------------------------------

    def set_tool_available(self, tool_name: str, available: bool) -> None:
        """Mark a catalogued tool available or unavailable (Requirement 18.3).

        An unavailable tool remains catalogued but is never enabled and any
        invocation against it is denied. Used by the MCP_Client to take a
        disconnected server's tools out of service without forgetting them, so
        they can be restored on reconnect. Marking an unknown tool is a no-op.
        """
        if tool_name not in self._tools:
            return
        if available:
            self._unavailable.discard(tool_name)
        else:
            self._unavailable.add(tool_name)

    def is_available(self, tool_name: str) -> bool:
        """True when ``tool_name`` is catalogued and not marked unavailable."""
        return tool_name in self._tools and tool_name not in self._unavailable

    # -- gating -------------------------------------------------------------

    def is_enabled(self, tool_name: str, scope: ToolScope) -> bool:
        """True when ``tool_name`` is catalogued and enabled in ``scope``.

        Resolves the tool's toolset against the scope's agent/run enable maps,
        with an agent-level disable taking precedence (Requirements 9.2, 9.3).
        Unknown tools are never enabled.
        """
        tool = self._tools.get(tool_name)
        if tool is None:
            return False
        if tool_name in self._unavailable:
            return False
        return scope.is_toolset_enabled(tool.toolset)

    # -- invocation ---------------------------------------------------------

    def invoke(
        self,
        tool_name: str,
        args: dict[str, Any],
        scope: ToolScope,
        *,
        run_scope: RunScope | None = None,
    ) -> ToolResult:
        """Invoke ``tool_name`` if enabled, otherwise deny and record it.

        When the tool is not enabled in ``scope`` (or is unknown), the call is
        denied and the denial is recorded in the run event history
        (Requirement 9.4). Enabled mutating tools are routed through the Sandbox
        path (Requirements 9.5, 21.1); enabled non-mutating tools run through
        their registered in-process handler.
        """
        args = args or {}
        tool = self._tools.get(tool_name)
        if tool is None:
            return self._deny(tool_name, run_scope, reason="tool is not registered")
        if tool_name in self._unavailable:
            return self._deny(
                tool_name,
                run_scope,
                reason="tool is currently unavailable",
            )
        if not scope.is_toolset_enabled(tool.toolset):
            return self._deny(
                tool_name,
                run_scope,
                reason=(
                    f"toolset {tool.toolset!r} is not enabled in the current scope"
                ),
            )

        if tool.mutating:
            return self._invoke_sandboxed(tool, args, run_scope)
        return self._invoke_in_process(tool, args)

    # -- internals ----------------------------------------------------------

    def _deny(
        self, tool_name: str, run_scope: RunScope | None, *, reason: str
    ) -> ToolResult:
        """Record a denied invocation in run history and return a denied result."""
        message = f"tool {tool_name!r} invocation denied: {reason}"
        if self._event_router is not None and run_scope is not None and run_scope.run_id:
            self._event_router.emit(
                run_scope.run_id,
                WorkflowEventType.TOOL_DENIED,
                message,
                payload={"tool": tool_name, "reason": reason},
            )
        else:
            # No run to attribute the denial to; still surface it for operators.
            LOGGER.info("%s (unattributed: no run scope/event router)", message)
        return ToolResult(
            tool_name=tool_name,
            ok=False,
            denied=True,
            error_message=reason,
        )

    def _invoke_sandboxed(
        self, tool: ToolSpec, args: dict[str, Any], run_scope: RunScope | None
    ) -> ToolResult:
        """Route a mutating tool through the Kernel-managed Sandbox path.

        Blocks with no host fallback when no sandbox executor is available
        (Requirements 9.5, 21.1, 21.2).
        """
        if self._sandbox_executor is None:
            raise SandboxRoutingBlocked(
                f"tool {tool.name!r} performs filesystem mutation or command "
                "execution and must run in a kernel-managed sandbox, but no "
                "sandbox executor is available; execution blocked with no host "
                "fallback"
            )
        try:
            output = self._sandbox_executor(tool, args, run_scope)
        except SandboxRoutingBlocked:
            raise
        except Exception as exc:  # noqa: BLE001 - reported as a failed invocation
            LOGGER.exception("sandboxed tool %r raised during execution", tool.name)
            return ToolResult(
                tool_name=tool.name,
                ok=False,
                sandboxed=True,
                error_message=str(exc),
            )
        return ToolResult(
            tool_name=tool.name,
            ok=True,
            output=output,
            sandboxed=True,
        )

    def _invoke_in_process(
        self, tool: ToolSpec, args: dict[str, Any]
    ) -> ToolResult:
        """Run a non-mutating tool through its registered in-process handler."""
        handler = self._handlers.get(tool.name)
        if handler is None:
            return ToolResult(
                tool_name=tool.name,
                ok=False,
                error_message=f"no handler registered for tool {tool.name!r}",
            )
        try:
            output = handler(args)
        except Exception as exc:  # noqa: BLE001 - reported as a failed invocation
            LOGGER.exception("tool %r handler raised during execution", tool.name)
            return ToolResult(
                tool_name=tool.name,
                ok=False,
                error_message=str(exc),
            )
        return ToolResult(tool_name=tool.name, ok=True, output=output)
