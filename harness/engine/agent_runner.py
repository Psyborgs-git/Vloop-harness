"""AgentOrchestrator — coordinates durable agent task runs.

An agent run follows the loop:
  1. Plan: use DSPy AgentPlanner to produce an ordered list of steps.
  2. Execute each step:
       - dspy_call  → invoke a DSPy module via the engine
       - tool_call  → dispatch to ToolRegistry
       - file_write → write a file via the filesystem tool
       - message    → record an intermediate status message
  3. For steps that require confirmation, pause the run and store a token.
  4. On resume (after confirmation), continue from the paused step.
  5. Record every step as an AgentRunStep in the database.

Usage (from a route handler)::

    orchestrator = AgentOrchestrator(main_process, db_session)
    run = await orchestrator.start(
        goal="Create a sentiment analysis DSPy component and a React UI for it",
        session_id="sess_abc",
        autonomy_mode="write_approval",
    )
    # run.id can be polled for status updates
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from harness.core.main_process import MainProcess


class AgentOrchestrator:
    """Coordinates agent runs: plan → execute → record → (resume)."""

    def __init__(self, main_process: MainProcess, db_session: AsyncSession) -> None:
        self._mp = main_process
        self._session = db_session

    # ── Public API ────────────────────────────────────────────────────────────

    async def start(
        self,
        goal: str,
        session_id: str | None = None,
        autonomy_mode: str = "suggest",
        context: str = "",
    ) -> Any:
        """Create a new AgentRun and begin (or queue) execution."""
        from harness.data.repository import Repository

        repo = Repository(self._session)
        run = await repo.create_agent_run(
            goal=goal,
            session_id=session_id,
            autonomy_mode=autonomy_mode,
        )

        # Schedule execution without blocking the caller
        asyncio.create_task(
            self._execute_run(run.id, goal, autonomy_mode, context),
            name=f"agent_run_{run.id}",
        )
        return run

    async def resume(self, run_id: str, confirmed_token: str | None = None) -> None:
        """Resume a paused run after confirmation or external trigger."""
        from harness.data.repository import Repository

        repo = Repository(self._session)
        run = await repo.get_agent_run(run_id)
        if run is None or run.status not in ("paused", "pending"):
            return

        await repo.update_agent_run(run_id, status="running")
        asyncio.create_task(
            self._resume_from_pause(run_id, confirmed_token),
            name=f"agent_run_{run_id}_resume",
        )

    async def cancel(self, run_id: str) -> None:
        from harness.data.repository import Repository

        repo = Repository(self._session)
        await repo.update_agent_run(run_id, status="cancelled")

    # ── Internal execution ────────────────────────────────────────────────────

    async def _execute_run(
        self,
        run_id: str,
        goal: str,
        autonomy_mode: str,
        context: str,
    ) -> None:
        from harness.data.db import get_session_factory
        from harness.data.repository import Repository

        factory = get_session_factory()
        async with factory() as session:
            repo = Repository(session)
            await repo.update_agent_run(run_id, status="running")

            try:
                plan_steps, summary = await self._plan(run_id, repo, goal, context)

                await repo.update_agent_run(
                    run_id,
                    plan=json.dumps(plan_steps, ensure_ascii=False),
                    status="running",
                )

                # If observe-only, stop after planning
                if autonomy_mode == "observe":
                    await repo.update_agent_run(
                        run_id,
                        status="completed",
                        result={"summary": summary, "steps": plan_steps},
                    )
                    return

                await self._run_steps(run_id, plan_steps, repo, autonomy_mode)

            except _RunPausedError as exc:
                await repo.update_agent_run(
                    run_id,
                    status="paused",
                    error=f"Waiting for confirmation: {exc.token}",
                )
            except Exception as exc:
                await repo.update_agent_run(
                    run_id, status="failed", error=str(exc)
                )

    async def _plan(
        self,
        run_id: str,
        repo: Any,
        goal: str,
        context: str,
    ) -> tuple[list[dict[str, Any]], str]:
        """Call AgentPlanner and record the planning step."""
        ai = self._mp.ai
        if not ai.is_ready:
            # No AI engine — return a single message step
            plan_steps: list[dict[str, Any]] = [
                {
                    "step_type": "message",
                    "description": "AI engine not configured; plan unavailable.",
                    "params": {},
                    "requires_confirmation": False,
                }
            ]
            await repo.add_run_step(
                run_id=run_id,
                step_type="plan",
                input_data={"goal": goal},
                output_data={"plan_json": json.dumps(plan_steps), "summary": ""},
            )
            return plan_steps, ""

        # Build context lists for the planner
        available_components: str = "[]"
        available_pipelines: str = "[]"
        available_tools: str = "[]"
        try:
            comp_catalog = [
                t.catalog_entry() for t in self._mp.tools.list_tools()
            ]
            available_tools = json.dumps(comp_catalog)
        except Exception:
            pass

        t0 = time.time()
        prediction = await ai.plan(
            goal=goal,
            available_components=available_components,
            available_pipelines=available_pipelines,
            available_tools=available_tools,
            context=context,
        )
        duration_ms = int((time.time() - t0) * 1000)

        raw_json = getattr(prediction, "plan_json", "[]")
        summary = getattr(prediction, "summary", "")
        try:
            plan_steps = json.loads(raw_json)
            if not isinstance(plan_steps, list):
                plan_steps = []
        except (json.JSONDecodeError, ValueError):
            plan_steps = []

        await repo.add_run_step(
            run_id=run_id,
            step_type="plan",
            input_data={"goal": goal, "context": context},
            output_data={"plan_json": raw_json, "summary": summary},
            duration_ms=duration_ms,
        )
        return plan_steps, summary

    async def _run_steps(
        self,
        run_id: str,
        steps: list[dict[str, Any]],
        repo: Any,
        autonomy_mode: str,
    ) -> None:
        """Execute each planned step in order with autonomy mode enforcement."""
        results: dict[str, Any] = {}

        for idx, step in enumerate(steps):
            step_type: str = step.get("step_type", "message")
            description: str = step.get("description", "")
            requires_confirmation: bool = step.get("requires_confirmation", False)
            step.get("params", {})
            tool_name: str | None = step.get("tool_name")

            # Enforce autonomy modes
            if autonomy_mode == "observe":
                # Observe-only: record step but don't execute
                await repo.add_run_step(
                    run_id=run_id,
                    step_type=step_type,
                    tool_name=tool_name,
                    input_data={"step": step, "index": idx},
                    output_data={"status": "observed", "description": description},
                    status="skipped",
                )
                continue

            if autonomy_mode == "suggest":
                # Suggest-only: record all planned steps without executing
                await repo.add_run_step(
                    run_id=run_id,
                    step_type=step_type,
                    tool_name=tool_name,
                    input_data={"step": step, "index": idx},
                    output_data={"status": "suggested", "description": description},
                    status="skipped",
                )
                continue

            # Check if step requires confirmation based on autonomy mode
            needs_confirmation = self._step_needs_confirmation(
                step, autonomy_mode, requires_confirmation
            )

            if needs_confirmation:
                token = f"agent_{run_id}_{idx}"
                await repo.add_run_step(
                    run_id=run_id,
                    step_type=step_type,
                    tool_name=tool_name,
                    input_data={"step": step, "index": idx},
                    status="pending",
                    confirmation_token=token,
                )
                raise _RunPausedError(token=token, step_index=idx)

            t0 = time.time()
            try:
                output = await self._execute_step(step, results, run_id)
                duration_ms = int((time.time() - t0) * 1000)
                results[f"step_{idx}"] = output
                await repo.add_run_step(
                    run_id=run_id,
                    step_type=step_type,
                    tool_name=tool_name,
                    input_data={"step": step, "index": idx},
                    output_data=output,
                    status="completed",
                    duration_ms=duration_ms,
                )
            except Exception as exc:
                duration_ms = int((time.time() - t0) * 1000)
                await repo.add_run_step(
                    run_id=run_id,
                    step_type=step_type,
                    tool_name=tool_name,
                    input_data={"step": step, "index": idx},
                    status="failed",
                    error=str(exc),
                    duration_ms=duration_ms,
                )
                # Continue on non-fatal step errors; let the run complete
                results[f"step_{idx}"] = {"error": str(exc)}

        await repo.update_agent_run(
            run_id,
            status="completed",
            result={"steps_executed": len(steps), "outputs": results},
        )

    def _step_needs_confirmation(
        self,
        step: dict[str, Any],
        autonomy_mode: str,
        requires_confirmation: bool,
    ) -> bool:
        """Determine if a step requires confirmation based on autonomy mode.

        Args:
            step: The step definition.
            autonomy_mode: Current autonomy mode.
            requires_confirmation: Whether the step is marked as requiring confirmation.

        Returns:
            True if confirmation is needed, False otherwise.
        """
        # Autonomous mode: no confirmations needed
        if autonomy_mode == "autonomous":
            return False

        # Step explicitly requires confirmation
        if requires_confirmation:
            return True

        # Write-approval mode: confirm file writes and destructive operations
        if autonomy_mode == "write_approval":
            step_type = step.get("step_type", "")
            tool_name = step.get("tool_name", "")

            # File writes, deletes, moves require confirmation
            if step_type == "file_write":
                return True
            if step_type == "tool_call" and tool_name in ("filesystem", "terminal"):
                operation = step.get("params", {}).get("operation", "")
                if operation in ("write", "delete", "move"):
                    return True

        # Test-approval mode: confirm test execution and deployment
        if autonomy_mode == "test_approval":
            step_type = step.get("step_type", "")
            if step_type == "tool_call":
                tool_name = step.get("tool_name", "")
                if tool_name == "terminal":
                    operation = step.get("params", {}).get("operation", "")
                    # Test commands typically involve pytest, npm test, etc.
                    if "test" in operation.lower():
                        return True

        return False

    async def _execute_step(
        self,
        step: dict[str, Any],
        accumulated: dict[str, Any],
        run_id: str,
    ) -> dict[str, Any]:
        """Dispatch a single plan step to the correct executor."""
        step_type = step.get("step_type", "message")
        params = step.get("params", {})
        tool_name = step.get("tool_name")

        if step_type == "tool_call" and tool_name:
            result = await self._mp.tools.execute(
                tool_name=tool_name,
                component_id=None,
                session_id=None,
                params=params,
            )
            return result.to_dict()

        if step_type == "file_write":
            result = await self._mp.tools.execute(
                tool_name="filesystem",
                component_id=None,
                session_id=None,
                params={"operation": "write", **params},
            )
            return result.to_dict()

        if step_type == "dspy_call":
            module_name: str = params.get("module", "reason")
            call_params = {k: v for k, v in params.items() if k != "module"}
            ai = self._mp.ai
            if not ai.is_ready:
                return {"error": "AI engine not ready"}
            method = getattr(ai, module_name, None)
            if method is None:
                return {"error": f"Unknown DSPy method: {module_name}"}
            prediction = await method(**call_params)
            return {"prediction": str(prediction)}

        # message or unknown — just record the description
        return {"message": step.get("description", "")}

    async def _resume_from_pause(
        self, run_id: str, confirmed_token: str | None
    ) -> None:
        """Re-execute remaining steps after a confirmation."""
        from harness.data.db import get_session_factory
        from harness.data.repository import Repository

        factory = get_session_factory()
        async with factory() as session:
            repo = Repository(session)
            run = await repo.get_agent_run(run_id)
            if run is None:
                return

            try:
                plan_steps = json.loads(run.plan) if run.plan else []
            except (json.JSONDecodeError, ValueError):
                plan_steps = []

            # Find the first step that's still pending
            completed_indices = {
                step.input_data.get("index")
                for step in (run.steps or [])
                if step.status == "completed" and step.input_data
            }
            pending_steps = [
                (i, s) for i, s in enumerate(plan_steps)
                if i not in completed_indices
            ]

            try:
                results: dict[str, Any] = {}
                for idx, step in pending_steps:
                    t0 = time.time()
                    try:
                        output = await self._execute_step(step, results, run_id)
                        duration_ms = int((time.time() - t0) * 1000)
                        results[f"step_{idx}"] = output
                        await repo.add_run_step(
                            run_id=run_id,
                            step_type=step.get("step_type", "message"),
                            tool_name=step.get("tool_name"),
                            input_data={"step": step, "index": idx},
                            output_data=output,
                            status="completed",
                            duration_ms=duration_ms,
                        )
                    except Exception as exc:
                        await repo.add_run_step(
                            run_id=run_id,
                            step_type=step.get("step_type", "message"),
                            tool_name=step.get("tool_name"),
                            input_data={"step": step, "index": idx},
                            status="failed",
                            error=str(exc),
                        )

                await repo.update_agent_run(
                    run_id,
                    status="completed",
                    result={"resumed": True, "outputs": results},
                )
            except _RunPausedError as exc:
                await repo.update_agent_run(
                    run_id,
                    status="paused",
                    error=f"Waiting for confirmation: {exc.token}",
                )
            except Exception as exc:
                await repo.update_agent_run(
                    run_id, status="failed", error=str(exc)
                )


class _RunPausedError(Exception):
    def __init__(self, token: str, step_index: int = 0) -> None:
        super().__init__(token)
        self.token = token
        self.step_index = step_index
