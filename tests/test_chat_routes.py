"""Integration tests for /api/chat/* routes.

Uses an in-memory SQLite database and a mocked MainProcess (AI not ready).

Covers:
  - GET /api/chat/sessions              (list)
  - POST /api/chat/sessions             (create)
  - GET /api/chat/sessions/{id}         (detail + 404)
  - PATCH /api/chat/sessions/{id}       (rename)
  - DELETE /api/chat/sessions/{id}      (204 + JSONL soft-retain)
  - GET /api/chat/sessions/{id}/messages
  - POST /api/chat/sessions/{id}/messages (no-AI path)
  - GET /api/chat/sessions/{id}/transcript
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from httpx import AsyncClient


# ── List sessions ─────────────────────────────────────────────────────────────


async def test_list_sessions_empty(client: AsyncClient) -> None:
    resp = await client.get("/api/chat/sessions")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_sessions_after_create(client: AsyncClient) -> None:
    await client.post("/api/chat/sessions", json={"title": "My Session"})
    resp = await client.get("/api/chat/sessions")
    assert resp.status_code == 200
    sessions = resp.json()
    assert len(sessions) == 1
    assert sessions[0]["title"] == "My Session"


# ── Create session ─────────────────────────────────────────────────────────────


async def test_create_session_default_title(client: AsyncClient) -> None:
    resp = await client.post("/api/chat/sessions", json={})
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "New Chat"
    assert "id" in data
    assert "created_at" in data


async def test_create_session_custom_title(client: AsyncClient) -> None:
    resp = await client.post("/api/chat/sessions", json={"title": "Custom"})
    assert resp.status_code == 201
    assert resp.json()["title"] == "Custom"


# ── Get session detail ─────────────────────────────────────────────────────────


async def test_get_session_detail(client: AsyncClient) -> None:
    created = (await client.post("/api/chat/sessions", json={"title": "Detail"})).json()
    resp = await client.get(f"/api/chat/sessions/{created['id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Detail"
    assert "messages" in data


async def test_get_session_404(client: AsyncClient) -> None:
    resp = await client.get("/api/chat/sessions/no-such-id")
    assert resp.status_code == 404


# ── Rename session ─────────────────────────────────────────────────────────────


async def test_rename_session(client: AsyncClient) -> None:
    created = (await client.post("/api/chat/sessions", json={"title": "Old"})).json()
    resp = await client.patch(
        f"/api/chat/sessions/{created['id']}", json={"title": "New"}
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "New"


async def test_rename_session_404(client: AsyncClient) -> None:
    resp = await client.patch("/api/chat/sessions/ghost", json={"title": "X"})
    assert resp.status_code == 404


# ── Delete session ─────────────────────────────────────────────────────────────


async def test_delete_session_returns_204(client: AsyncClient) -> None:
    created = (await client.post("/api/chat/sessions", json={})).json()
    resp = await client.delete(f"/api/chat/sessions/{created['id']}")
    assert resp.status_code == 204


async def test_delete_session_removes_from_list(client: AsyncClient) -> None:
    created = (await client.post("/api/chat/sessions", json={})).json()
    await client.delete(f"/api/chat/sessions/{created['id']}")
    sessions = (await client.get("/api/chat/sessions")).json()
    assert all(s["id"] != created["id"] for s in sessions)


async def test_delete_session_404(client: AsyncClient) -> None:
    resp = await client.delete("/api/chat/sessions/ghost-id")
    assert resp.status_code == 404


async def test_delete_session_soft_retains_jsonl(
    client: AsyncClient,
    test_app,
    tmp_path: Path,
) -> None:
    """After DELETE, the JSONL transcript must be renamed to .jsonl.deleted."""
    storage = test_app.state.vloop_storage
    created = (await client.post("/api/chat/sessions", json={})).json()
    session_id = created["id"]

    # Create a JSONL file (simulating a previous send_message)
    storage.append_chat_message(session_id, {"id": "m1", "role": "user", "content": "hi"})
    assert storage.chat_session_file(session_id).exists()

    await client.delete(f"/api/chat/sessions/{session_id}")

    # Original file must be gone; .deleted file must exist
    jsonl_path = storage.chat_session_file(session_id)
    deleted_path = jsonl_path.parent / (jsonl_path.name + ".deleted")
    assert not jsonl_path.exists()
    assert deleted_path.exists()


# ── List messages ─────────────────────────────────────────────────────────────


async def test_list_messages_empty(client: AsyncClient) -> None:
    created = (await client.post("/api/chat/sessions", json={})).json()
    resp = await client.get(f"/api/chat/sessions/{created['id']}/messages")
    assert resp.status_code == 200
    assert resp.json() == []


# ── Send message (no-AI path) ─────────────────────────────────────────────────


async def test_send_message_no_ai_returns_assistant_message(client: AsyncClient) -> None:
    created = (await client.post("/api/chat/sessions", json={})).json()
    resp = await client.post(
        f"/api/chat/sessions/{created['id']}/messages",
        json={"content": "Hello"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "assistant"
    assert "not configured" in data["content"].lower()


async def test_send_message_stores_user_message(client: AsyncClient) -> None:
    created = (await client.post("/api/chat/sessions", json={})).json()
    session_id = created["id"]
    await client.post(f"/api/chat/sessions/{session_id}/messages", json={"content": "Hi"})
    messages = (await client.get(f"/api/chat/sessions/{session_id}/messages")).json()
    assert len(messages) == 2  # user + assistant
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hi"


async def test_send_message_writes_jsonl(client: AsyncClient, test_app) -> None:
    """Both user and assistant messages should be written to JSONL after send."""
    storage = test_app.state.vloop_storage
    created = (await client.post("/api/chat/sessions", json={})).json()
    session_id = created["id"]
    await client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={"content": "JSONL test"},
    )
    lines = storage.read_chat_session(session_id)
    # Dual-write: user line + assistant line
    assert len(lines) == 2
    roles = [l["role"] for l in lines]
    assert "user" in roles
    assert "assistant" in roles


async def test_send_message_jsonl_schema_v1(client: AsyncClient, test_app) -> None:
    """Each JSONL line must contain id, session_id, role, content, meta, created_at, v."""
    storage = test_app.state.vloop_storage
    created = (await client.post("/api/chat/sessions", json={})).json()
    session_id = created["id"]
    await client.post(
        f"/api/chat/sessions/{session_id}/messages", json={"content": "schema"}
    )
    lines = storage.read_chat_session(session_id)
    required_keys = {"id", "session_id", "role", "content", "meta", "created_at", "v"}
    for line in lines:
        assert required_keys.issubset(line.keys()), f"Missing keys in {line}"
    assert all(line["v"] == 1 for line in lines)


async def test_send_message_to_nonexistent_session_returns_404(
    client: AsyncClient,
) -> None:
    resp = await client.post("/api/chat/sessions/ghost/messages", json={"content": "hi"})
    assert resp.status_code == 404


# ── Transcript endpoint ────────────────────────────────────────────────────────


async def test_transcript_empty_for_new_session(client: AsyncClient) -> None:
    created = (await client.post("/api/chat/sessions", json={})).json()
    resp = await client.get(f"/api/chat/sessions/{created['id']}/transcript")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_transcript_returns_jsonl_lines_after_message(
    client: AsyncClient, test_app
) -> None:
    created = (await client.post("/api/chat/sessions", json={})).json()
    session_id = created["id"]
    await client.post(
        f"/api/chat/sessions/{session_id}/messages", json={"content": "transcript test"}
    )
    resp = await client.get(f"/api/chat/sessions/{session_id}/transcript")
    assert resp.status_code == 200
    lines = resp.json()
    assert len(lines) == 2  # user + assistant
    assert lines[0]["role"] == "user"
    assert lines[0]["content"] == "transcript test"


async def test_transcript_404_for_missing_session(client: AsyncClient) -> None:
    resp = await client.get("/api/chat/sessions/no-such/transcript")
    assert resp.status_code == 404


# ── Multiple sessions isolation ────────────────────────────────────────────────


async def test_sessions_are_isolated(client: AsyncClient, test_app) -> None:
    """Messages sent to one session must not appear in another."""
    s1 = (await client.post("/api/chat/sessions", json={"title": "S1"})).json()
    s2 = (await client.post("/api/chat/sessions", json={"title": "S2"})).json()
    await client.post(f"/api/chat/sessions/{s1['id']}/messages", json={"content": "only in s1"})
    msgs_s2 = (await client.get(f"/api/chat/sessions/{s2['id']}/messages")).json()
    assert msgs_s2 == []


# ── Response shape ─────────────────────────────────────────────────────────────


async def test_session_response_has_required_fields(client: AsyncClient) -> None:
    resp = await client.post("/api/chat/sessions", json={"title": "Shape"})
    data = resp.json()
    for key in ("id", "title", "created_at", "updated_at"):
        assert key in data, f"Missing key: {key}"


async def test_message_response_has_required_fields(client: AsyncClient) -> None:
    created = (await client.post("/api/chat/sessions", json={})).json()
    resp = await client.post(
        f"/api/chat/sessions/{created['id']}/messages", json={"content": "fields"}
    )
    data = resp.json()
    for key in ("id", "session_id", "role", "content", "meta", "created_at"):
        assert key in data, f"Missing key: {key}"
