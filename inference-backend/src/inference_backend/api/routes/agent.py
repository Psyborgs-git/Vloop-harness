from __future__ import annotations

import asyncio
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ...api.ws.stream import broadcast
from ...dspy_core.agent_loops import (
    chain_of_thought,
    react,
    plan_execute,
    tool_call,
    multi_agent,
)

router = APIRouter()

LOOPS = {
    "chain_of_thought": chain_of_thought.run,
    "react": react.run,
    "plan_execute": plan_execute.run,
    "tool_call": tool_call.run,
    "multi_agent": multi_agent.run,
}


class AgentRunRequest(BaseModel):
    agent: str
    task: str
    config: dict[str, Any] | None = None


@router.get("/agent/loops")
async def list_loops():
    return list(LOOPS.keys())


@router.post("/agent/run")
async def agent_run(req: AgentRunRequest, request: Request):
    loop_fn = LOOPS.get(req.agent)
    if loop_fn is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown agent loop '{req.agent}'. Available: {list(LOOPS.keys())}",
        )

    run_id = str(uuid.uuid4())
    db = request.app.state.agent_db
    event_loop = asyncio.get_running_loop()
    step_counter: list[int] = [0]

    # Persist run start + broadcast to live-streaming WebSocket clients
    await db.insert_agent_run(run_id, req.agent, req.task)
    await broadcast("agent.step", {
        "run_id": run_id,
        "step_index": 0,
        "step_type": "start",
        "content": req.task,
    })

    def step_callback(step_index: int, step_type: str, content: str) -> None:
        """Called from the sync DSPy thread to publish a live streaming event.

        Uses ``run_coroutine_threadsafe`` to schedule coroutines onto the main
        asyncio event loop from the worker thread.
        """
        idx = step_index + 1
        step_counter[0] = idx
        sid = str(uuid.uuid4())
        asyncio.run_coroutine_threadsafe(
            asyncio.gather(
                broadcast(
                    "agent.step",
                    {
                        "run_id": run_id,
                        "step_index": idx,
                        "step_type": step_type,
                        "content": content,
                    },
                ),
                db.insert_agent_step(sid, run_id, idx, step_type, content),
            ),
            event_loop,
        )

    try:
        # Run the synchronous DSPy loop in a thread pool so the event loop
        # stays unblocked while agent steps stream live.
        result = await event_loop.run_in_executor(
            None,
            lambda: loop_fn(task=req.task, config=req.config, step_callback=step_callback),
        )
        await db.finish_agent_run(run_id, "completed")
        await broadcast("agent.complete", {
            "run_id": run_id,
            "answer": result.get("answer", ""),
            "total_steps": step_counter[0],
        })
        return {"run_id": run_id, **result}
    except Exception as exc:
        await db.finish_agent_run(run_id, "failed")
        await broadcast("agent.error", {"run_id": run_id, "error": str(exc)})
        raise HTTPException(status_code=500, detail=str(exc)) from exc
