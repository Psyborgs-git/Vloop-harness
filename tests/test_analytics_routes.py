"""Integration tests for /api/analytics routes."""

from __future__ import annotations

import json
from datetime import date

from httpx import AsyncClient


async def test_record_client_events_accepts_batch(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/analytics/events",
        json={
            "events": [
                {
                    "event_type": "screen_view",
                    "component_id": "root",
                    "occurred_at": "2026-05-10T00:00:00Z",
                    "data": {"screen": "dashboard.chat"},
                },
                {
                    "event_type": "action_click",
                    "data": {"action_id": "chat.tools.open", "screen": "dashboard.chat.session"},
                },
            ]
        },
    )

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "accepted": 2}


async def test_record_client_events_dual_writes_jsonl(client: AsyncClient, test_app) -> None:
    resp = await client.post(
        "/api/analytics/events",
        json={
            "events": [
                {
                    "event_type": "action_click",
                    "data": {"action_id": "chat.view.new", "screen": "dashboard.chat.session"},
                }
            ]
        },
    )
    assert resp.status_code == 200

    telemetry_file = test_app.state.vloop_storage.project_dir / "telemetry" / f"{date.today().isoformat()}.jsonl"
    rows = [json.loads(line) for line in telemetry_file.read_text().splitlines()]
    assert rows[-1]["type"] == "action_click"
    assert rows[-1]["data"]["action_id"] == "chat.view.new"
    assert rows[-1]["data"]["source"] == "client"
