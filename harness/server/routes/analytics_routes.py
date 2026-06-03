"""Client analytics and telemetry ingestion routes."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from harness.data.db import get_session
from harness.data.repository import Repository

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


class ClientTelemetryEvent(BaseModel):
    event_type: str = Field(min_length=1, max_length=100)
    data: dict[str, Any] = Field(default_factory=dict)
    component_id: str | None = Field(default=None, max_length=64)
    occurred_at: str | None = None


class ClientTelemetryBatch(BaseModel):
    events: list[ClientTelemetryEvent] = Field(min_length=1, max_length=100)


class ClientTelemetryResponse(BaseModel):
    status: Literal["ok"]
    accepted: int


@router.post("/events", response_model=ClientTelemetryResponse)
async def record_client_events(
    body: ClientTelemetryBatch,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> ClientTelemetryResponse:
    """Persist client-side analytics without making telemetry failures fatal."""
    repo = Repository(db)
    accepted = 0

    for event in body.events:
        payload = {
            **event.data,
            "source": "client",
            "occurred_at": event.occurred_at,
        }
        await repo.record_telemetry(event.event_type, component_id=event.component_id, data=payload)
        accepted += 1

        try:
            storage = request.app.state.vloop_storage
            storage.log_telemetry(event.event_type, payload)
        except Exception:
            pass

    return ClientTelemetryResponse(status="ok", accepted=accepted)
