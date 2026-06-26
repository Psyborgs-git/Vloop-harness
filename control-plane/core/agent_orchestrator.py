"""Agent orchestrator — CRUD, invocation dispatch, and usage statistics."""

from __future__ import annotations

import threading
import uuid
from typing import TYPE_CHECKING, Any

from core.agent_invoker import append_event, execute_invocation
from core.agent_normalizer import (
    normalize_agent_payload,
    row_to_agent,
    row_to_invocation,
    validate_invocation_inputs,
)
from core.agent_templates import TEMPLATES
from core.helpers import from_json, now_iso, to_json

if TYPE_CHECKING:
    from core.provider_service import ProviderService

    from core.database import DatabaseBackend
    from core.vector_store import VectorStore


class AgentOrchestrator:
    """Manages agent CRUD, invocation lifecycle, and usage analytics."""

    def __init__(
        self,
        state: DatabaseBackend,
        providers: ProviderService,
        vector_store: VectorStore | None = None,
    ) -> None:
        self._state = state
        self._providers = providers
        self._vector_store = vector_store

    # -- agent CRUD ----------------------------------------------------------

    def list_agents(self) -> list[dict[str, Any]]:
        rows = self._state.fetch_all(
            "SELECT * FROM agents ORDER BY updated_at DESC, name ASC"
        )
        agents: list[dict[str, Any]] = []
        for row in rows:
            agent = row_to_agent(row)
            if agent is not None:
                agents.append(agent)
        return agents

    def list_templates(self) -> list[dict[str, Any]]:
        return [template.to_dict() for template in TEMPLATES]

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        row = self._state.fetch_one("SELECT * FROM agents WHERE id = ?", (agent_id,))
        return row_to_agent(row) if row else None

    def save_agent(
        self, payload: dict[str, Any], agent_id: str | None = None
    ) -> dict[str, Any]:
        normalized = normalize_agent_payload(payload, agent_id, self._providers)
        existing = self._state.fetch_one(
            "SELECT * FROM agents WHERE id = ?", (normalized["id"],)
        )
        now = now_iso()

        if existing is None:
            self._state.execute(
                """
                INSERT INTO agents (
                    id, slug, name, description, enabled, instructions, reasoning_mode,
                    input_fields_json, output_mode, output_field_name, output_schema_json,
                    default_provider_id, model_override, temperature, max_tokens,
                    revision, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized["id"],
                    normalized["slug"],
                    normalized["name"],
                    normalized["description"],
                    int(normalized["enabled"]),
                    normalized["instructions"],
                    normalized["reasoningMode"],
                    to_json(normalized["inputFields"]),
                    normalized["outputMode"],
                    normalized["outputFieldName"],
                    to_json(normalized["outputSchema"]),
                    normalized["defaultProviderId"],
                    normalized["modelOverride"],
                    normalized["temperature"],
                    normalized["maxTokens"],
                    1,
                    now,
                    now,
                ),
            )
        else:
            self._state.execute(
                """
                UPDATE agents
                SET slug = ?, name = ?, description = ?, enabled = ?, instructions = ?, reasoning_mode = ?,
                    input_fields_json = ?, output_mode = ?, output_field_name = ?, output_schema_json = ?,
                    default_provider_id = ?, model_override = ?, temperature = ?, max_tokens = ?,
                    revision = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    normalized["slug"],
                    normalized["name"],
                    normalized["description"],
                    int(normalized["enabled"]),
                    normalized["instructions"],
                    normalized["reasoningMode"],
                    to_json(normalized["inputFields"]),
                    normalized["outputMode"],
                    normalized["outputFieldName"],
                    to_json(normalized["outputSchema"]),
                    normalized["defaultProviderId"],
                    normalized["modelOverride"],
                    normalized["temperature"],
                    normalized["maxTokens"],
                    int(existing["revision"]) + 1,
                    now,
                    normalized["id"],
                ),
            )

        saved = self.get_agent(normalized["id"])
        if saved is None:
            raise RuntimeError(
                "agent save succeeded but the agent could not be reloaded"
            )
        return saved

    def delete_agent(self, agent_id: str) -> None:
        self._state.execute("DELETE FROM agents WHERE id = ?", (agent_id,))

    def validate_agent(
        self, payload: dict[str, Any], agent_id: str | None = None
    ) -> dict[str, Any]:
        normalized = normalize_agent_payload(payload, agent_id, self._providers)
        return {"valid": True, "normalized": normalized}

    # -- invocations ---------------------------------------------------------

    def list_invocations(self, agent_id: str | None = None) -> list[dict[str, Any]]:
        if agent_id:
            rows = self._state.fetch_all(
                "SELECT * FROM invocations WHERE agent_id = ? ORDER BY created_at DESC LIMIT 50",
                (agent_id,),
            )
        else:
            rows = self._state.fetch_all(
                "SELECT * FROM invocations ORDER BY created_at DESC LIMIT 50"
            )
        invocations: list[dict[str, Any]] = []
        for row in rows:
            invocation = row_to_invocation(row)
            if invocation is not None:
                invocations.append(invocation)
        return invocations

    def get_invocation(self, invocation_id: str) -> dict[str, Any] | None:
        row = self._state.fetch_one(
            "SELECT * FROM invocations WHERE id = ?", (invocation_id,)
        )
        return row_to_invocation(row) if row else None

    def get_invocation_events(self, invocation_id: str) -> list[dict[str, Any]]:
        rows = self._state.fetch_all(
            "SELECT * FROM invocation_events WHERE invocation_id = ? ORDER BY seq ASC",
            (invocation_id,),
        )
        return [
            {
                "seq": int(row["seq"]),
                "type": row["type"],
                "message": row["message"],
                "payload": from_json(row["payload_json"], {}),
                "elapsedMs": row["elapsed_ms"],
                "createdAt": row["created_at"],
            }
            for row in rows
        ]

    def invoke_agent(self, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        agent = self.get_agent(agent_id)
        if agent is None:
            raise KeyError(f"agent `{agent_id}` was not found")
        if not agent["enabled"]:
            raise ValueError(f"agent `{agent['name']}` is disabled")

        inputs = payload.get("inputs") or {}
        if not isinstance(inputs, dict):
            raise ValueError("invocation inputs must be an object")
        overrides = payload.get("overrides") or {}
        if not isinstance(overrides, dict):
            raise ValueError("invocation overrides must be an object")

        validate_invocation_inputs(agent, inputs)
        provider_id = str(overrides.get("providerId") or agent["defaultProviderId"])
        provider = self._providers.get_provider(provider_id)
        if provider is None:
            raise ValueError(f"provider `{provider_id}` was not found")
        if not provider["enabled"]:
            raise ValueError(f"provider `{provider['name']}` is disabled")

        invocation_id = str(uuid.uuid4())
        now = now_iso()
        self._state.execute(
            """
            INSERT INTO invocations (
                id, agent_id, agent_revision, provider_id, provider_revision, status,
                inputs_json, overrides_json, resolved_model, resolved_config_json,
                output_text, output_json, reasoning_text, usage_json, error_code,
                error_message, created_at, started_at, finished_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                invocation_id,
                agent["id"],
                agent["revision"],
                provider["id"],
                provider["revision"],
                "queued",
                to_json(inputs),
                to_json(overrides),
                str(
                    overrides.get("model")
                    or agent.get("modelOverride")
                    or provider.get("defaultModel")
                    or ""
                ),
                to_json({}),
                None,
                None,
                None,
                None,
                None,
                None,
                now,
                None,
                None,
            ),
        )
        append_event(
            self._state,
            invocation_id,
            "queued",
            "Invocation queued",
            {"agentId": agent_id},
        )

        threading.Thread(
            target=execute_invocation,
            args=(invocation_id, agent, provider, inputs, overrides),
            kwargs={
                "providers": self._providers,
                "state": self._state,
                "append_event": lambda *a, **kw: append_event(self._state, *a, **kw),
            },
            name=f"vloop-agent-invocation-{invocation_id}",
            daemon=True,
        ).start()

        invocation = self.get_invocation(invocation_id)
        if invocation is None:
            raise RuntimeError("invocation was created but could not be reloaded")
        return invocation

    # -- usage stats ---------------------------------------------------------

    def get_usage_stats(self) -> dict[str, Any]:
        invocations = self._state.fetch_all(
            "SELECT id, agent_id, provider_id, resolved_model, usage_json, created_at FROM invocations WHERE usage_json IS NOT NULL ORDER BY created_at DESC"
        )
        agents = self._state.fetch_all("SELECT id, slug, name FROM agents")
        providers = self._state.fetch_all(
            "SELECT id, name, provider_type FROM providers"
        )

        agent_map: dict[str, dict[str, Any]] = {}
        for row in agents:
            agent_map[row["id"]] = {
                "agentId": row["id"],
                "agentName": row["name"] or row["slug"],
                "invocationCount": 0,
                "totalTokens": 0,
            }

        provider_map: dict[str, dict[str, Any]] = {}
        for row in providers:
            provider_map[row["id"]] = {
                "providerId": row["id"],
                "providerName": row["name"],
                "providerType": row["provider_type"],
                "invocationCount": 0,
                "totalTokens": 0,
            }

        total_tokens = 0
        total_prompt_tokens = 0
        total_completion_tokens = 0
        recent: list[dict[str, Any]] = []

        for inv in invocations:
            usage = from_json(inv["usage_json"], {})
            if not usage:
                continue
            prompt = int(usage.get("prompt_tokens") or 0)
            completion = int(usage.get("completion_tokens") or 0)
            tok = int(usage.get("total_tokens") or prompt + completion or 0)

            total_tokens += tok
            total_prompt_tokens += prompt
            total_completion_tokens += completion

            agent_id = inv["agent_id"]
            if agent_id in agent_map:
                agent_map[agent_id]["invocationCount"] += 1
                agent_map[agent_id]["totalTokens"] += tok

            provider_id = inv["provider_id"]
            if provider_id in provider_map:
                provider_map[provider_id]["invocationCount"] += 1
                provider_map[provider_id]["totalTokens"] += tok

            if len(recent) < 20:
                recent.append(
                    {
                        "invocationId": inv["id"],
                        "agentId": agent_id,
                        "agentName": agent_map.get(agent_id, {}).get("agentName", ""),
                        "providerId": provider_id,
                        "providerName": provider_map.get(provider_id, {}).get(
                            "providerName", ""
                        ),
                        "providerType": provider_map.get(provider_id, {}).get(
                            "providerType", ""
                        ),
                        "model": inv["resolved_model"],
                        "promptTokens": prompt,
                        "completionTokens": completion,
                        "totalTokens": tok,
                        "createdAt": inv["created_at"],
                    }
                )

        return {
            "totalTokens": total_tokens,
            "totalPromptTokens": total_prompt_tokens,
            "totalCompletionTokens": total_completion_tokens,
            "invocationCount": len(invocations),
            "byProvider": sorted(
                provider_map.values(), key=lambda x: x["totalTokens"], reverse=True
            ),
            "byAgent": sorted(
                agent_map.values(), key=lambda x: x["totalTokens"], reverse=True
            ),
            "recentInvocations": recent,
        }
