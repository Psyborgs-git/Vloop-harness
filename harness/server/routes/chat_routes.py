"""REST routes for the root chat interface.

Endpoints
─────────
  GET    /api/chat/sessions               — list all chat sessions
  POST   /api/chat/sessions               — create a new session
  GET    /api/chat/sessions/{id}          — get session + messages
  PATCH  /api/chat/sessions/{id}          — rename a session
  DELETE /api/chat/sessions/{id}          — delete a session and its messages
  GET    /api/chat/sessions/{id}/messages — get messages for a session
  POST   /api/chat/sessions/{id}/messages — send a message, get AI reply
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from harness.data.db import get_session
from harness.data.repository import Repository

router = APIRouter(prefix="/api/chat", tags=["chat"])


# ── Request / Response models ─────────────────────────────────────────────────


class SessionCreateRequest(BaseModel):
    title: str = "New Chat"


class SessionPatchRequest(BaseModel):
    title: str


class SendMessageRequest(BaseModel):
    content: str


# ── Chat session CRUD ─────────────────────────────────────────────────────────


@router.get("/sessions")
async def list_sessions(db: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    repo = Repository(db)
    sessions = await repo.list_sessions()
    return [_session_to_dict(s) for s in sessions]


@router.post("/sessions", status_code=201)
async def create_session(
    body: SessionCreateRequest,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    repo = Repository(db)
    session = await repo.create_session(title=body.title)
    return _session_to_dict(session)


@router.get("/sessions/{session_id}")
async def get_session_detail(
    session_id: str,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    repo = Repository(db)
    session = await repo.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        **_session_to_dict(session),
        "messages": [_message_to_dict(m) for m in (session.messages or [])],
    }


@router.patch("/sessions/{session_id}")
async def rename_session(
    session_id: str,
    body: SessionPatchRequest,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    repo = Repository(db)
    session = await repo.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    await repo.update_session_title(session_id, body.title)
    session.title = body.title
    return _session_to_dict(session)


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    db: AsyncSession = Depends(get_session),
) -> None:
    repo = Repository(db)
    session = await repo.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    await repo.delete_session(session_id)


@router.get("/sessions/{session_id}/messages")
async def list_messages(
    session_id: str,
    db: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    repo = Repository(db)
    messages = await repo.get_messages(session_id)
    return [_message_to_dict(m) for m in messages]


# ── Message send + AI reply ───────────────────────────────────────────────────


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: str,
    body: SendMessageRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    repo = Repository(db)

    session = await repo.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Persist user message
    user_msg = await repo.add_message(session_id, "user", body.content)

    # Fetch context for the AI
    all_messages = await repo.get_messages(session_id)
    components = await repo.list_components()
    pipelines = await repo.list_pipelines()

    history = _format_history(all_messages[:-1])  # exclude the just-added user message
    available_comps = json.dumps(
        [{"id": c.id, "name": c.name, "description": c.description} for c in components]
    )
    available_pipes = json.dumps(
        [{"id": p.id, "name": p.name, "description": p.description} for p in pipelines]
    )

    # Call the AI engine
    mp = request.app.state.main_process
    ai_response_text = ""
    component_code = ""
    pipeline_config = ""
    saved_component_id: str | None = None
    saved_pipeline_id: str | None = None

    if mp.ai.is_ready:
        try:
            prediction = await mp.ai.chat(
                history=history,
                user_message=body.content,
                available_components=available_comps,
                available_pipelines=available_pipes,
            )
            ai_response_text = getattr(prediction, "response", "") or ""
            component_code = getattr(prediction, "component_code", "") or ""
            pipeline_config = getattr(prediction, "pipeline_config", "") or ""
        except Exception as exc:
            ai_response_text = f"I encountered an error: {exc}"
    else:
        ai_response_text = (
            "The AI engine is not configured. Please add a provider in Settings "
            "and set it as the default to enable AI-powered responses."
        )

    # Auto-save generated component if code was returned
    if component_code.strip():
        try:
            from harness.engine.component_registry import DSPyComponentRegistry
            from harness.data.models import DSPyComponentDef

            sig_fields = DSPyComponentRegistry.extract_signature_fields(component_code)
            comp_name = _extract_module_class_name(component_code) or "GeneratedComponent"
            comp_id = f"comp_{uuid.uuid4().hex[:10]}"

            comp = DSPyComponentDef(
                id=comp_id,
                name=comp_name,
                description=f"Generated during chat session: {session.title}",
                code=component_code,
                module_type="ChainOfThought",
                signature_fields=sig_fields,
            )
            registry = request.app.state.component_registry
            registry.compile(comp)
            await repo.save_component(comp)
            saved_component_id = comp_id
        except Exception:
            pass  # Don't fail the message on component save errors

    # Auto-save generated pipeline if config was returned
    if pipeline_config.strip():
        try:
            pipe_data = json.loads(pipeline_config)
            from harness.data.models import PipelineDef

            pipe_id = f"pipe_{uuid.uuid4().hex[:10]}"
            pipeline = PipelineDef(
                id=pipe_id,
                name=pipe_data.get("name", "Generated Pipeline"),
                description=pipe_data.get("description", ""),
                steps=pipe_data.get("steps", []),
            )
            await repo.save_pipeline(pipeline)
            saved_pipeline_id = pipe_id
        except Exception:
            pass

    # Build the assistant's full reply with metadata in the DB meta field
    meta: dict[str, Any] = {}
    if component_code:
        meta["component_code"] = component_code
    if saved_component_id:
        meta["saved_component_id"] = saved_component_id
    if pipeline_config:
        meta["pipeline_config"] = pipeline_config
    if saved_pipeline_id:
        meta["saved_pipeline_id"] = saved_pipeline_id

    ai_msg = await repo.add_message(
        session_id, "assistant", ai_response_text, meta=meta or None
    )

    # Log telemetry
    try:
        storage = request.app.state.vloop_storage
        storage.log_telemetry("chat_message", {"session_id": session_id})
    except Exception:
        pass

    return {
        **_message_to_dict(ai_msg),
        "saved_component_id": saved_component_id,
        "saved_pipeline_id": saved_pipeline_id,
    }


# ── Serialisation helpers ─────────────────────────────────────────────────────


def _session_to_dict(s: Any) -> dict[str, Any]:
    return {
        "id": s.id,
        "title": s.title,
        "created_at": s.created_at.isoformat(),
        "updated_at": s.updated_at.isoformat(),
    }


def _message_to_dict(m: Any) -> dict[str, Any]:
    return {
        "id": m.id,
        "session_id": m.session_id,
        "role": m.role,
        "content": m.content,
        "meta": m.meta or {},
        "created_at": m.created_at.isoformat(),
    }


def _format_history(messages: list[Any]) -> str:
    parts: list[str] = []
    for m in messages:
        role = m.role.capitalize()
        parts.append(f"{role}: {m.content}")
    return "\n".join(parts)


def _extract_module_class_name(code: str) -> str | None:
    """Extract the first dspy.Module subclass name from source code."""
    import ast

    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    if "Module" in ast.unparse(base) and "Signature" not in ast.unparse(base):
                        return node.name
    except Exception:
        pass
    return None
