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
        import os
        import httpx
        import time
        from harness.core.secret_redaction import redact_any
        from harness.core.metrics import record_tool_execution

        ai_url = os.environ.get("RUST_BASE_AI_URL", "")
        if ai_url:
            rust_url = ai_url.rsplit("/v1", 1)[0]
            async with httpx.AsyncClient() as client:
                try:
                    res = await client.post(
                        f"{rust_url}/harness/tools/execute",
                        json={
                            "tool_name": tool_name,
                            "component_id": component_id,
                            "session_id": session_id,
                            "params": params or {},
                        },
                        timeout=60.0
                    )
                    if res.status_code == 202:
                        from harness.tools.exceptions import ConfirmationRequired
                        data = res.json()
                        raise ConfirmationRequired(
                            token=data["token"],
                            description=data["description"],
                            risk_level=data["risk_level"]
                        )
                    elif res.status_code == 200:
                        data = res.json()
                        return ToolResult(
                            success=data.get("success", False),
                            output=data.get("output"),
                            error=data.get("error"),
                            exit_code=data.get("exit_code"),
                            metadata=data.get("metadata", {})
                        )
                    else:
                        return ToolResult(
                            success=False,
                            error=f"Rust host returned status code {res.status_code}: {res.text}"
                        )
                except httpx.HTTPError as exc:
                    return ToolResult(
                        success=False,
                        error=f"Error communicating with Rust host: {exc}"
                    )

        tool = self._tools.get(tool_name)
        if tool is None:
            return ToolResult(
                success=False,
                error=f"Unknown tool: {tool_name!r}",
            )

        # Record execution start time for tracing
        start_time = time.time()

        try:
            result = await tool.execute(component_id, session_id, params or {})

            # Add duration to metadata
            duration_ms = int((time.time() - start_time) * 1000)
            result.metadata["duration_ms"] = duration_ms
            result.metadata["risk_level"] = tool.risk_level

            # Record metrics
            record_tool_execution(tool_name, duration_ms, True, component_id)

            # Record tool trace asynchronously (non-blocking)
            self._record_trace(
                tool_name=tool_name,
                component_id=component_id,
                session_id=session_id,
                params=params or {},
                result=result,
                duration_ms=duration_ms,
            )

            return result
        except Exception as exc:
            # Record failed execution
            duration_ms = int((time.time() - start_time) * 1000)
            error_result = ToolResult(
                success=False,
                error=str(exc),
                metadata={"duration_ms": duration_ms, "risk_level": tool.risk_level}
            )

            # Record metrics for failure
            record_tool_execution(tool_name, duration_ms, False, component_id)

            self._record_trace(
                tool_name=tool_name,
                component_id=component_id,
                session_id=session_id,
                params=params or {},
                result=error_result,
                duration_ms=duration_ms,
            )

            raise

    def _record_trace(
        self,
        tool_name: str,
        component_id: str | None,
        session_id: str | None,
        params: dict[str, Any],
        result: ToolResult,
        duration_ms: int,
    ) -> None:
        """Record a tool execution trace to the database."""
        import asyncio
        from harness.data.db import get_session_factory
        from harness.data.models import ToolTrace

        async def _save_trace():
            try:
                factory = get_session_factory()
                async with factory() as session:
                    from harness.core.secret_redaction import redact_any

                    trace = ToolTrace(
                        tool_name=tool_name,
                        component_id=component_id,
                        session_id=session_id,
                        inputs=redact_any(params),
                        outputs=redact_any(result.to_dict(redact_secrets=False)),
                        risk_level=result.metadata.get("risk_level", "safe"),
                        duration_ms=duration_ms,
                        success=result.success,
                    )
                    session.add(trace)
                    await session.commit()
            except Exception:
                # Don't fail the tool execution if tracing fails
                pass

        # Fire and forget - don't block tool execution
        asyncio.create_task(_save_trace())

    # ── Catalog ───────────────────────────────────────────────────────────────

    def catalog(self) -> list[dict[str, Any]]:
        """Return a list of catalog entries for all registered tools."""
        return [t.catalog_entry() for t in self._tools.values()]
