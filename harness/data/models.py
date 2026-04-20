"""SQLAlchemy ORM models for all VLoop persistent data.

Tables
──────
  chat_sessions       — top-level conversation threads
  chat_messages       — individual messages within a session
  dspy_components     — generated/saved DSPy component definitions
  pipelines           — ordered compositions of DSPy components
  provider_configs    — AI inference provider configurations (API keys encrypted)
  telemetry           — structured usage events
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from harness.data.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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
    """An ordered composition of DSPy components.

    ``steps`` is a list of ``{"component_id": str, "input_map": {...}}`` dicts.
    ``input_map`` maps the step's input field names to either a previous step's
    output field (by name) or a literal string value.
    """

    __tablename__ = "pipelines"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
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


# ── Telemetry ─────────────────────────────────────────────────────────────────


class TelemetryEvent(Base):
    __tablename__ = "telemetry"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    event_type: Mapped[str] = mapped_column(String(100))
    component_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
