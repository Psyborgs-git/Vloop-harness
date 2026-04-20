"""ToolRegistry — central catalog and dispatcher for all tool implementations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from harness.tools.base_tool import AbstractTool, ToolResult

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
        return await tool.execute(component_id, session_id, params or {})

    # ── Catalog ───────────────────────────────────────────────────────────────

    def catalog(self) -> list[dict[str, Any]]:
        """Return a list of catalog entries for all registered tools."""
        return [t.catalog_entry() for t in self._tools.values()]
