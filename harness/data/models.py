"""SQLAlchemy ORM models for all VLoop persistent data.

Tables
──────
  chat_sessions       — top-level conversation threads
  chat_messages       — individual messages within a session
  dspy_components     — generated/saved DSPy component definitions
  pipelines           — ordered compositions of DSPy components
  provider_configs    — AI inference provider configurations (API keys encrypted)
  generated_views     — AI-generated React view stubs
  telemetry           — structured usage events
  agent_runs          — durable agent task runs
  agent_run_steps     — append-only audit log of each step in a run
  app_manifests       — links backend components/pipelines to React views
  tool_traces         — enriched records of every tool call
  component_versions  — point-in-time snapshots of DSPy component definitions (for rollback)
  eval_datasets       — input/output example pairs for evaluating DSPy components
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from harness.data.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_uuid() -> str:
    return str(uuid.uuid4())


# ── Chat ──────────────────────────────────────────────────────────────────────


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    title: Mapped[str] = mapped_column(String(255), default="New Chat")
    provider_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    messages: Mapped[list[ChatMessage]] = relationship(
        "ChatMessage", back_populates="session", cascade="all, delete-orphan"
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chat_sessions.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20))  # user | assistant | system
    content: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    session: Mapped[ChatSession] = relationship("ChatSession", back_populates="messages")


# ── DSPy components ───────────────────────────────────────────────────────────


class DSPyComponentDef(Base):
    """A user-created or AI-generated DSPy Module definition.

    ``code`` holds the full Python source (Signature class + Module class).
    ``signature_fields`` mirrors the field metadata for the UI without parsing code.
    """

    __tablename__ = "dspy_components"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    signature_fields: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict  # {"inputs": [...], "outputs": [...]}
    )
    code: Mapped[str] = mapped_column(Text)
    module_type: Mapped[str] = mapped_column(String(50), default="ChainOfThought")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


# ── Pipelines ─────────────────────────────────────────────────────────────────


class PipelineDef(Base):
    """An ordered composition of DSPy components and/or tool steps.

    ``steps`` is a list of step dicts.  Each step must have a ``"type"`` key:

    Component step (default when ``"type"`` is absent)::

        {
            "type": "component",
            "component_id": "comp_abc",
            "config": {"input_map": {}}
        }

    Tool step::

        {
            "type": "tool",
            "tool_name": "terminal",
            "config": {
                "command": "pytest {test_path}",
                "cwd_relative": ".",
                "timeout": 60,
                "input_map": {"test_path": "file_path"}
            }
        }

    ``tool_permissions`` declares the ceiling of permissions this pipeline may
    exercise (list of ``Permission`` value strings). It acts as a cap, not an
    escalation mechanism.
    """

    __tablename__ = "pipelines"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    tool_permissions: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


# ── Provider configurations ───────────────────────────────────────────────────


class ProviderConfigDB(Base):
    """An AI inference provider (Ollama, Anthropic, OpenAI, or custom).

    ``encrypted_api_key`` stores the Fernet-encrypted API key ciphertext.
    It is empty for providers that don't require a key (local Ollama).
    """

    __tablename__ = "provider_configs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    provider_type: Mapped[str] = mapped_column(String(50))  # ollama|anthropic|openai|custom
    model: Mapped[str] = mapped_column(String(255))
    base_url: Mapped[str] = mapped_column(String(500), default="")
    encrypted_api_key: Mapped[str] = mapped_column(Text, default="")
    extra_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


# ── Generated React views ─────────────────────────────────────────────────────


class GeneratedView(Base):
    """An AI-generated React view stub.

    ``react_code`` holds the TSX source written to disk under
    ``react/src/components/generated/{component_name}/App.tsx``.
    ``view_spec`` contains the LLM's natural-language spec/rationale.
    ``file_path`` records the absolute disk path of the written stub (if any).
    """

    __tablename__ = "generated_views"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    name: Mapped[str] = mapped_column(String(255))
    component_name: Mapped[str] = mapped_column(String(64))
    react_code: Mapped[str] = mapped_column(Text, default="")
    view_spec: Mapped[str] = mapped_column(Text, default="")
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ── Telemetry ─────────────────────────────────────────────────────────────────


class TelemetryEvent(Base):
    __tablename__ = "telemetry"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    event_type: Mapped[str] = mapped_column(String(100))
    component_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ── Agent runs ─────────────────────────────────────────────────────────────────


class AgentRun(Base):
    """A durable record of a single agent task execution.

    ``goal``         — natural-language description of what the agent was asked to do.
    ``plan``         — the agent's generated plan (may be updated as the run progresses).
    ``status``       — one of: pending | running | paused | completed | cancelled | failed.
    ``autonomy_mode``— one of: observe | suggest | write_approval | test_approval | autonomous.
    ``session_id``   — optional chat session that triggered this run.
    ``result``       — final structured result from the run.
    ``error``        — last error message if the run failed.
    """

    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    goal: Mapped[str] = mapped_column(Text)
    plan: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    autonomy_mode: Mapped[str] = mapped_column(String(20), default="suggest")
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    steps: Mapped[list[AgentRunStep]] = relationship(
        "AgentRunStep", back_populates="run", cascade="all, delete-orphan", order_by="AgentRunStep.created_at"
    )


class AgentRunStep(Base):
    """A single step in an agent run — append-only audit log.

    ``step_type``    — one of: plan | dspy_call | tool_call | file_write | confirmation | message | error.
    ``tool_name``    — populated for tool_call steps.
    ``input_data``   — inputs passed to this step.
    ``output_data``  — outputs produced by this step.
    ``status``       — one of: pending | running | completed | failed | skipped.
    ``confirmation_token`` — non-null when this step is waiting for human approval.
    """

    __tablename__ = "agent_run_steps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("agent_runs.id"), nullable=False)
    step_type: Mapped[str] = mapped_column(String(30))
    tool_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    output_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="completed")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmation_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    run: Mapped[AgentRun] = relationship("AgentRun", back_populates="steps")


# ── App manifests ──────────────────────────────────────────────────────────────


class AppManifest(Base):
    """Links a backend (Python component or DSPy pipeline) to one or more React views.

    ``backend_type``   — "component" | "pipeline" | "dspy_module".
    ``backend_id``     — ID of the backend object (component, pipeline, or dspy_component).
    ``react_views``    — list of GeneratedView IDs or component_names this manifest includes.
    ``permissions``    — list of Permission value strings this app may exercise.
    ``state_schema``   — JSON schema describing the backend's expected state.
    ``status``         — one of: draft | validated | active | archived.
    ``agent_run_id``   — optional run that created this manifest.
    """

    __tablename__ = "app_manifests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    backend_type: Mapped[str] = mapped_column(String(30), default="pipeline")
    backend_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    react_views: Mapped[list[str]] = mapped_column(JSON, default=list)
    permissions: Mapped[list[str]] = mapped_column(JSON, default=list)
    state_schema: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    agent_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


# ── Tool traces ────────────────────────────────────────────────────────────────


class ToolTrace(Base):
    """Enriched record of a single tool call.

    ``tool_name``        — "terminal" | "filesystem" | "browser" | "database".
    ``component_id``     — component that invoked the tool (null for direct UI calls).
    ``session_id``       — chat session context (if any).
    ``run_step_id``      — optional AgentRunStep that triggered this call.
    ``inputs``           — sanitized input params (secrets redacted).
    ``outputs``          — sanitized output (secrets redacted, truncated at 8 KiB).
    ``risk_level``       — "safe" | "caution" | "destructive".
    ``confirmation_token``— set when this trace was preceded by a confirmation.
    ``duration_ms``      — wall-clock execution time.
    ``success``          — whether the call succeeded.
    """

    __tablename__ = "tool_traces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    tool_name: Mapped[str] = mapped_column(String(64))
    component_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    run_step_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    inputs: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    outputs: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    risk_level: Mapped[str] = mapped_column(String(20), default="safe")
    confirmation_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ── Component versions ─────────────────────────────────────────────────────────


class ComponentVersion(Base):
    """A point-in-time snapshot of a DSPyComponentDef for versioning and rollback.

    ``component_id``   — ID of the source component (no FK so deleted comps can still be versioned).
    ``version_number`` — monotonically increasing per component_id.
    ``change_summary`` — human-readable description of what changed in this version.
    """

    __tablename__ = "component_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    component_id: Mapped[str] = mapped_column(String(64), nullable=False)
    version_number: Mapped[int] = mapped_column(default=1)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    code: Mapped[str] = mapped_column(Text)
    module_type: Mapped[str] = mapped_column(String(50), default="ChainOfThought")
    change_summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ViewVersion(Base):
    """A point-in-time snapshot of a React view for versioning and rollback.

    ``view_id``        — ID of the source GeneratedView (no FK so deleted views can still be versioned).
    ``version_number`` — monotonically increasing per view_id.
    ``file_path``      — relative path to the view file in the React project.
    ``source``         — complete TypeScript/React source code.
    ``prompt``         — AI prompt used to generate this view (if applicable).
    ``agent_run_id``   — optional agent run that created this version.
    ``change_summary`` — human-readable description of what changed in this version.
    """

    __tablename__ = "view_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    view_id: Mapped[str] = mapped_column(String(64), nullable=False)
    version_number: Mapped[int] = mapped_column(default=1)
    file_path: Mapped[str] = mapped_column(String(512))
    source: Mapped[str] = mapped_column(Text)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    change_summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ── Eval datasets ──────────────────────────────────────────────────────────────


class EvalDataset(Base):
    """A set of input/output example pairs for evaluating a DSPy component.

    ``examples`` is a list of dicts with the shape::

        {"inputs": {"field": "value", ...}, "expected_outputs": {"field": "value", ...}}
    """

    __tablename__ = "eval_datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    component_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    examples: Mapped[list[dict]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
