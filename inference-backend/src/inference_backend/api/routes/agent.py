from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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
async def agent_run(req: AgentRunRequest):
    loop_fn = LOOPS.get(req.agent)
    if loop_fn is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown agent loop '{req.agent}'. Available: {list(LOOPS.keys())}",
        )
    run_id = str(uuid.uuid4())
    try:
        result = loop_fn(task=req.task, config=req.config)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"run_id": run_id, **result}
