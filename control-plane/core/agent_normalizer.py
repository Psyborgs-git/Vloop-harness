"""Agent payload normalization and row-mapping utilities."""

from __future__ import annotations

import re
import uuid
from typing import TYPE_CHECKING, Any

from core.helpers import from_json

if TYPE_CHECKING:
    from core.provider_service import ProviderService

_SAFE_FIELD_NAME = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")
_SAFE_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def normalize_agent_payload(
    payload: dict[str, Any],
    agent_id: str | None,
    providers: ProviderService,
) -> dict[str, Any]:
    """Validate and normalize an agent create/update payload."""
    name = str(payload.get("name") or "").strip()
    if len(name) < 2:
        raise ValueError("agent name must be at least 2 characters")

    slug = str(payload.get("slug") or _slugify(name)).strip()
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
        label = str(field.get("label") or field_name.replace("_", " ").title()).strip()
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
    provider = providers.get_provider(provider_id)
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


def validate_invocation_inputs(agent: dict[str, Any], inputs: dict[str, Any]) -> None:
    """Verify that required input fields are present and non-empty."""
    for field in agent["inputFields"]:
        if field["required"] and not str(inputs.get(field["name"], "")).strip():
            raise ValueError(f"input field `{field['label']}` is required")


def row_to_agent(row: dict[str, Any] | None) -> dict[str, Any] | None:
    """Map a database row to a frontend-facing agent dict."""
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


def row_to_invocation(row: dict[str, Any] | None) -> dict[str, Any] | None:
    """Map a database row to a frontend-facing invocation dict."""
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


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "agent"
