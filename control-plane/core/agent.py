"""Custom DSPy agent definitions and invocation runtime."""

from __future__ import annotations

import ast
import json
import re
import threading
import uuid
from dataclasses import dataclass
from typing import Any

from core.gateway import ProviderService
from core.store import SQLiteState, from_json, now_iso, to_json

_SAFE_FIELD_NAME = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")
_SAFE_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")


@dataclass(slots=True)
class AgentTemplate:
    id: str
    name: str
    description: str
    instructions: str
    input_fields: list[dict[str, Any]]
    output_mode: str
    output_field_name: str
    output_schema: dict[str, Any] | None
    reasoning_mode: str
    temperature: float
    max_tokens: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "instructions": self.instructions,
            "inputFields": self.input_fields,
            "outputMode": self.output_mode,
            "outputFieldName": self.output_field_name,
            "outputSchema": self.output_schema,
            "reasoningMode": self.reasoning_mode,
            "temperature": self.temperature,
            "maxTokens": self.max_tokens,
        }


TEMPLATES = [
    AgentTemplate(
        id="summarizer",
        name="Release-note summarizer",
        description="Turn long updates into concise, stakeholder-ready bullets.",
        instructions="You are a concise product operations agent. Summarize the supplied material into clear bullets, surface risks, and keep the tone practical.",
        input_fields=[
            {
                "name": "source_text",
                "label": "Source text",
                "description": "The raw material to summarize.",
                "required": True,
            },
            {
                "name": "audience",
                "label": "Audience",
                "description": "Who the summary is for.",
                "required": False,
            },
        ],
        output_mode="text",
        output_field_name="response",
        output_schema=None,
        reasoning_mode="chain_of_thought",
        temperature=0.2,
        max_tokens=700,
    ),
    AgentTemplate(
        id="json_briefer",
        name="Structured research briefer",
        description="Return a machine-readable brief from arbitrary input.",
        instructions="You are a research synthesis agent. Extract the main theme, the critical constraints, and the next actions from the supplied material.",
        input_fields=[
            {
                "name": "topic",
                "label": "Topic",
                "description": "The topic or request to analyze.",
                "required": True,
            },
            {
                "name": "context",
                "label": "Context",
                "description": "Any extra context, notes, or source material.",
                "required": False,
            },
        ],
        output_mode="json",
        output_field_name="response",
        output_schema={
            "theme": "string",
            "constraints": ["string"],
            "next_actions": ["string"],
        },
        reasoning_mode="chain_of_thought",
        temperature=0.1,
        max_tokens=900,
    ),
]


class AgentOrchestrator:
    def __init__(self, state: SQLiteState, providers: ProviderService) -> None:
        self._state = state
        self._providers = providers

    def list_agents(self) -> list[dict[str, Any]]:
        rows = self._state.fetch_all(
            "SELECT * FROM agents ORDER BY updated_at DESC, name ASC"
        )
        agents: list[dict[str, Any]] = []
        for row in rows:
            agent = self._row_to_agent(row)
            if agent is not None:
                agents.append(agent)
        return agents

    def list_templates(self) -> list[dict[str, Any]]:
        return [template.to_dict() for template in TEMPLATES]

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        row = self._state.fetch_one("SELECT * FROM agents WHERE id = ?", (agent_id,))
        return self._row_to_agent(row) if row else None

    def save_agent(
        self, payload: dict[str, Any], agent_id: str | None = None
    ) -> dict[str, Any]:
        normalized = self._normalize_agent_payload(payload, agent_id)
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
        normalized = self._normalize_agent_payload(payload, agent_id)
        return {"valid": True, "normalized": normalized}

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
            invocation = self._row_to_invocation(row)
            if invocation is not None:
                invocations.append(invocation)
        return invocations

    def get_invocation(self, invocation_id: str) -> dict[str, Any] | None:
        row = self._state.fetch_one(
            "SELECT * FROM invocations WHERE id = ?", (invocation_id,)
        )
        return self._row_to_invocation(row) if row else None

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

        self._validate_invocation_inputs(agent, inputs)
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
        self._append_event(
            invocation_id, "queued", "Invocation queued", {"agentId": agent_id}
        )

        threading.Thread(
            target=self._execute_invocation,
            args=(invocation_id, agent, provider, inputs, overrides),
            name=f"vloop-agent-invocation-{invocation_id}",
            daemon=True,
        ).start()

        invocation = self.get_invocation(invocation_id)
        if invocation is None:
            raise RuntimeError("invocation was created but could not be reloaded")
        return invocation

    def _execute_invocation(
        self,
        invocation_id: str,
        agent: dict[str, Any],
        provider: dict[str, Any],
        inputs: dict[str, Any],
        overrides: dict[str, Any],
    ) -> None:
        started_at = now_iso()
        resolved_model = str(
            overrides.get("model")
            or agent.get("modelOverride")
            or provider.get("defaultModel")
            or ""
        ).strip()
        temperature_source = (
            overrides["temperature"]
            if overrides.get("temperature") is not None
            else agent["temperature"]
        )
        token_source = (
            overrides["maxTokens"]
            if overrides.get("maxTokens") is not None
            else agent["maxTokens"]
        )
        resolved_temperature = float(temperature_source)
        resolved_max_tokens = int(token_source)
        resolved_config = {
            "providerId": provider["id"],
            "model": resolved_model,
            "temperature": resolved_temperature,
            "maxTokens": resolved_max_tokens,
            "reasoningMode": agent["reasoningMode"],
            "outputMode": agent["outputMode"],
        }

        self._state.execute(
            "UPDATE invocations SET status = ?, started_at = ?, resolved_model = ?, resolved_config_json = ? WHERE id = ?",
            (
                "running",
                started_at,
                resolved_model,
                to_json(resolved_config),
                invocation_id,
            ),
        )
        self._append_event(
            invocation_id, "started", "Invocation started", resolved_config
        )

        try:
            lm = self._providers.build_lm(
                provider["id"],
                model_override=resolved_model,
                temperature=resolved_temperature,
                max_tokens=resolved_max_tokens,
            )
            self._append_event(
                invocation_id,
                "provider_resolved",
                "Provider and model resolved",
                {"providerName": provider["name"], "model": resolved_model},
            )

            request_text = self._build_request_text(agent, inputs)
            self._append_event(
                invocation_id,
                "validated",
                "Structured request compiled for DSPy",
                {"inputCount": len(inputs)},
            )

            output_text, output_json, reasoning_text, usage = self._run_dspy_program(
                agent, lm, request_text
            )

            finished_at = now_iso()
            self._state.execute(
                "UPDATE invocations SET status = ?, output_text = ?, output_json = ?, reasoning_text = ?, usage_json = ?, finished_at = ?, error_code = NULL, error_message = NULL WHERE id = ?",
                (
                    "succeeded",
                    output_text,
                    to_json(output_json) if output_json is not None else None,
                    reasoning_text,
                    to_json(usage) if usage is not None else None,
                    finished_at,
                    invocation_id,
                ),
            )
            self._append_event(
                invocation_id,
                "completed",
                "Agent invocation completed",
                {"hasReasoning": bool(reasoning_text)},
            )
        except Exception as exc:  # pragma: no cover - runtime path
            finished_at = now_iso()
            self._state.execute(
                "UPDATE invocations SET status = ?, error_code = ?, error_message = ?, finished_at = ? WHERE id = ?",
                (
                    "failed",
                    exc.__class__.__name__,
                    str(exc),
                    finished_at,
                    invocation_id,
                ),
            )
            self._append_event(
                invocation_id,
                "failed",
                "Agent invocation failed",
                {"error": str(exc), "errorCode": exc.__class__.__name__},
            )

    def _run_dspy_program(
        self, agent: dict[str, Any], lm: Any, request_text: str
    ) -> tuple[str, dict[str, Any] | None, str | None, dict[str, Any] | None]:
        import importlib

        dspy = importlib.import_module("dspy")
        output_field_name = str(agent.get("outputFieldName") or "response")
        signature = f"request -> {output_field_name}"
        module = (
            dspy.ChainOfThought(signature)
            if agent["reasoningMode"] == "chain_of_thought"
            else dspy.Predict(signature)
        )
        module.set_lm(lm)
        result = module(request=request_text)

        field_value = getattr(result, output_field_name, "")
        reasoning_text = str(getattr(result, "reasoning", "")).strip() or None
        output_json: dict[str, Any] | None = None
        if agent["outputMode"] == "json":
            if isinstance(field_value, dict):
                output_json = field_value
                response_text = json.dumps(output_json, ensure_ascii=False)
            else:
                response_text = str(field_value).strip()
                output_json = self._parse_json_output(response_text)
                response_text = json.dumps(output_json, ensure_ascii=False)
        else:
            response_text = str(field_value).strip()

        usage = None
        history = getattr(lm, "history", None)
        if history:
            latest = history[-1]
            usage = latest.get("usage") if isinstance(latest, dict) else None

        return response_text, output_json, reasoning_text, usage

    def _parse_json_output(self, response_text: str) -> dict[str, Any]:
        candidate = response_text.strip()
        if candidate.startswith("```"):
            candidate = candidate.strip("`")
            if candidate.startswith("json"):
                candidate = candidate[4:].strip()
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            try:
                parsed = ast.literal_eval(candidate)
            except (ValueError, SyntaxError) as exc:
                raise ValueError(
                    "agent was configured for JSON output, but the model response was not valid JSON"
                ) from exc
        if not isinstance(parsed, dict):
            raise ValueError(
                "JSON-output agents must return an object at the top level"
            )
        return parsed

    def _build_request_text(self, agent: dict[str, Any], inputs: dict[str, Any]) -> str:
        sections = [agent["instructions"].strip(), "", "Structured inputs:"]
        for field in agent["inputFields"]:
            label = field["label"]
            value = str(inputs.get(field["name"], "")).strip()
            sections.append(f"- {label} ({field['name']}): {value or '(not provided)'}")
            if field.get("description"):
                sections.append(f"  Guidance: {field['description']}")

        sections.extend(
            [
                "",
                f"Return the final answer in the `{agent['outputFieldName']}` field.",
            ]
        )

        if agent["outputMode"] == "json" and agent.get("outputSchema"):
            sections.extend(
                [
                    "",
                    "Return valid JSON only. Do not wrap it in markdown fences.",
                    "JSON shape guidance:",
                    json.dumps(agent["outputSchema"], ensure_ascii=False, indent=2),
                ]
            )

        return "\n".join(sections).strip()

    def _append_event(
        self, invocation_id: str, event_type: str, message: str, payload: dict[str, Any]
    ) -> None:
        existing = self._state.fetch_one(
            "SELECT COALESCE(MAX(seq), 0) AS seq FROM invocation_events WHERE invocation_id = ?",
            (invocation_id,),
        )
        next_seq = int(existing["seq"]) + 1 if existing else 1
        self._state.execute(
            "INSERT INTO invocation_events (invocation_id, seq, type, message, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (invocation_id, next_seq, event_type, message, to_json(payload), now_iso()),
        )

    def _normalize_agent_payload(
        self, payload: dict[str, Any], agent_id: str | None
    ) -> dict[str, Any]:
        name = str(payload.get("name") or "").strip()
        if len(name) < 2:
            raise ValueError("agent name must be at least 2 characters")

        slug = str(payload.get("slug") or self._slugify(name)).strip()
        if not _SAFE_SLUG.match(slug):
            raise ValueError(
                "agent slug may only contain lowercase letters, numbers, and hyphens"
            )

        instructions = str(payload.get("instructions") or "").strip()
        if len(instructions) < 10:
            raise ValueError("agent instructions must be at least 10 characters")

        reasoning_mode = str(payload.get("reasoningMode") or "predict").strip()
        if reasoning_mode not in {"predict", "chain_of_thought"}:
            raise ValueError("reasoningMode must be `predict` or `chain_of_thought`")

        output_mode = str(payload.get("outputMode") or "text").strip()
        if output_mode not in {"text", "json"}:
            raise ValueError("outputMode must be `text` or `json`")

        output_field_name = (
            str(payload.get("outputFieldName") or "response").strip() or "response"
        )
        if not _SAFE_FIELD_NAME.match(output_field_name):
            raise ValueError("outputFieldName must be a safe identifier")
        if output_field_name in {"request", "reasoning"}:
            raise ValueError(
                "outputFieldName cannot be `request` or `reasoning` because DSPy reserves those fields"
            )

        input_fields = payload.get("inputFields") or []
        if not isinstance(input_fields, list) or not input_fields:
            raise ValueError("agent inputFields must contain at least one field")
        normalized_fields = []
        seen_names: set[str] = set()
        for field in input_fields:
            field_name = str(field.get("name") or "").strip()
            if not _SAFE_FIELD_NAME.match(field_name):
                raise ValueError(
                    f"input field `{field_name or '<empty>'}` is not a safe identifier"
                )
            if field_name in seen_names:
                raise ValueError(f"input field `{field_name}` is duplicated")
            seen_names.add(field_name)
            label = str(
                field.get("label") or field_name.replace("_", " ").title()
            ).strip()
            normalized_fields.append(
                {
                    "name": field_name,
                    "label": label,
                    "description": str(field.get("description") or "").strip() or None,
                    "required": bool(field.get("required", True)),
                }
            )

        output_schema = payload.get("outputSchema")
        if output_mode == "json":
            if not isinstance(output_schema, dict) or not output_schema:
                raise ValueError(
                    "JSON-output agents require a non-empty outputSchema object"
                )
        else:
            output_schema = None

        provider_id = str(
            payload.get("defaultProviderId") or payload.get("default_provider_id") or ""
        ).strip()
        provider = self._providers.get_provider(provider_id)
        if provider is None:
            raise ValueError("defaultProviderId must reference an existing provider")

        temperature = float(payload.get("temperature", 0.2))
        max_tokens = int(payload.get("maxTokens", 700))
        if max_tokens < 32:
            raise ValueError("maxTokens must be at least 32")

        return {
            "id": agent_id or str(uuid.uuid4()),
            "slug": slug,
            "name": name,
            "description": str(payload.get("description") or "").strip() or None,
            "enabled": bool(payload.get("enabled", True)),
            "instructions": instructions,
            "reasoningMode": reasoning_mode,
            "inputFields": normalized_fields,
            "outputMode": output_mode,
            "outputFieldName": output_field_name,
            "outputSchema": output_schema,
            "defaultProviderId": provider_id,
            "modelOverride": str(payload.get("modelOverride") or "").strip() or None,
            "temperature": temperature,
            "maxTokens": max_tokens,
        }

    def _validate_invocation_inputs(
        self, agent: dict[str, Any], inputs: dict[str, Any]
    ) -> None:
        for field in agent["inputFields"]:
            if field["required"] and not str(inputs.get(field["name"], "")).strip():
                raise ValueError(f"input field `{field['label']}` is required")

    def _row_to_agent(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {
            "id": row["id"],
            "slug": row["slug"],
            "name": row["name"],
            "description": row["description"],
            "enabled": bool(row["enabled"]),
            "instructions": row["instructions"],
            "reasoningMode": row["reasoning_mode"],
            "inputFields": from_json(row["input_fields_json"], []),
            "outputMode": row["output_mode"],
            "outputFieldName": row["output_field_name"],
            "outputSchema": from_json(row["output_schema_json"], None),
            "defaultProviderId": row["default_provider_id"],
            "modelOverride": row["model_override"],
            "temperature": float(row["temperature"]),
            "maxTokens": int(row["max_tokens"]),
            "revision": int(row["revision"]),
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def _row_to_invocation(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {
            "id": row["id"],
            "agentId": row["agent_id"],
            "agentRevision": int(row["agent_revision"]),
            "providerId": row["provider_id"],
            "providerRevision": int(row["provider_revision"]),
            "status": row["status"],
            "inputs": from_json(row["inputs_json"], {}),
            "overrides": from_json(row["overrides_json"], {}),
            "resolvedModel": row["resolved_model"],
            "resolvedConfig": from_json(row["resolved_config_json"], {}),
            "outputText": row["output_text"],
            "outputJson": from_json(row["output_json"], None),
            "reasoningText": row["reasoning_text"],
            "usage": from_json(row["usage_json"], None),
            "errorCode": row["error_code"],
            "errorMessage": row["error_message"],
            "createdAt": row["created_at"],
            "startedAt": row["started_at"],
            "finishedAt": row["finished_at"],
        }

    def _slugify(self, value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
        return slug or "agent"
