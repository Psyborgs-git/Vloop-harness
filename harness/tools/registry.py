"""ToolRegistry — central catalog and dispatcher for all tool implementations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from harness.tools.base_tool import AbstractTool, ToolResult
from harness.vloop.redaction import redact_secrets
from harness.data.db import get_session_factory
from harness.data.repository import Repository

if TYPE_CHECKING:
    from harness.core.main_process import MainProcess


class ToolRegistry:
    """Owns all registered tool instances and dispatches ``execute`` calls."""

    def __init__(self, main_process: "MainProcess") -> None:
        self._mp = main_process
        self._tools: dict[str, AbstractTool] = {}

    # ── Registration ──────────────────────────────────────────────────────────

    def register(self, tool: AbstractTool) -> None:
        """Register a tool instance. Overwrites any previous registration."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> AbstractTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[AbstractTool]:
        return list(self._tools.values())

    # ── Dispatch ──────────────────────────────────────────────────────────────

    async def execute(
        self,
        tool_name: str,
        component_id: str | None = None,
        session_id: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> ToolResult:
        """Look up *tool_name* and delegate to its ``execute`` method."""
        tool = self._tools.get(tool_name)
        if tool is None:
            return ToolResult(
                success=False,
                error=f"Unknown tool: {tool_name!r}",
            )

        safe_params = params or {}

        # Determine token for pending confirmations if present
        confirmation_token = safe_params.get("_confirmation_token")

        # Execute the tool
        result = await tool.execute(component_id, session_id, safe_params)

        # Save trace
        try:
            factory = get_session_factory()
            async with factory() as session:
                repo = Repository(session)
                await repo.record_tool_trace(
                    tool_name=tool_name,
                    inputs=redact_secrets(safe_params),
                    outputs=redact_secrets(result.to_dict()),
                    component_id=component_id,
                    session_id=session_id,
                    run_step_id=None,
                    risk_level=tool.risk_level,
                    confirmation_token=confirmation_token,
                    duration_ms=result.metadata.get("duration_ms"),
                    success=result.success,
                )
        except Exception:
            # We don't want tool tracing failures to bring down the whole app
            self._mp.logger.error(f"Failed to record tool trace for {tool_name}")

        return result

    # ── Catalog ───────────────────────────────────────────────────────────────

    def catalog(self) -> list[dict[str, Any]]:
        """Return a list of catalog entries for all registered tools."""
        return [t.catalog_entry() for t in self._tools.values()]
