"""Dynamic provider configuration and LM factory for the control plane."""

from __future__ import annotations

import importlib
import json
import re
import uuid
from dataclasses import asdict, dataclass
from types import SimpleNamespace
from typing import Any

from core.store import SQLiteState, now_iso


@dataclass(slots=True)
class ProviderTypeSpec:
    key: str
    label: str
    description: str
    secret_modes: list[str]
    default_model: str
    model_examples: list[str]
    api_base_hint: str | None = None
    api_version_hint: str | None = None
    requires_secret: bool = True
    local_only_http: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


PROVIDER_TYPES: dict[str, ProviderTypeSpec] = {
    "mock": ProviderTypeSpec(
        key="mock",
        label="VLoop Mock LM",
        description="Local deterministic DSPy-compatible provider for smoke testing and first-run exploration.",
        secret_modes=["none"],
        default_model="mock/echo-agent",
        model_examples=["mock/echo-agent"],
        requires_secret=False,
    ),
    "ollama": ProviderTypeSpec(
        key="ollama",
        label="Ollama",
        description="Use a local Ollama daemon over loopback without any cloud credentials.",
        secret_modes=["none"],
        default_model="ollama/llama3.2",
        model_examples=["ollama/llama3.2", "ollama/qwen2.5:7b"],
        api_base_hint="http://127.0.0.1:11434",
        requires_secret=False,
        local_only_http=True,
    ),
    "openai": ProviderTypeSpec(
        key="openai",
        label="OpenAI",
        description="Use OpenAI-hosted chat or responses models through LiteLLM.",
        secret_modes=["env", "session"],
        default_model="openai/gpt-4o-mini",
        model_examples=["openai/gpt-4o-mini", "openai/gpt-4.1-mini"],
    ),
    "anthropic": ProviderTypeSpec(
        key="anthropic",
        label="Anthropic",
        description="Use Anthropic Claude models through LiteLLM.",
        secret_modes=["env", "session"],
        default_model="anthropic/claude-3-5-sonnet-latest",
        model_examples=[
            "anthropic/claude-3-5-sonnet-latest",
            "anthropic/claude-3-5-haiku-latest",
        ],
    ),
    "openrouter": ProviderTypeSpec(
        key="openrouter",
        label="OpenRouter",
        description="Route OpenAI-compatible traffic through OpenRouter with a provider-prefixed model string.",
        secret_modes=["env", "session"],
        default_model="openrouter/openai/gpt-4o-mini",
        model_examples=[
            "openrouter/openai/gpt-4o-mini",
            "openrouter/anthropic/claude-3.5-sonnet",
        ],
        api_base_hint="https://openrouter.ai/api/v1",
    ),
    "azure": ProviderTypeSpec(
        key="azure",
        label="Azure OpenAI",
        description="Use Azure OpenAI deployments via LiteLLM with an Azure-style deployment model string.",
        secret_modes=["env", "session"],
        default_model="azure/my-deployment",
        model_examples=["azure/my-deployment"],
        api_base_hint="https://your-resource.openai.azure.com",
        api_version_hint="2024-10-21",
    ),
}


class ProviderService:
    def __init__(self, state: SQLiteState) -> None:
        self._state = state
        self._session_secrets: dict[str, str] = {}

    def provider_catalog(self) -> list[dict[str, Any]]:
        return [spec.to_dict() for spec in PROVIDER_TYPES.values()]

    def list_providers(self) -> list[dict[str, Any]]:
        rows = self._state.fetch_all(
            "SELECT * FROM providers ORDER BY updated_at DESC, name ASC"
        )
        providers: list[dict[str, Any]] = []
        for row in rows:
            provider = self._row_to_provider(row)
            if provider is not None:
                providers.append(provider)
        return providers

    def get_provider(self, provider_id: str) -> dict[str, Any] | None:
        row = self._state.fetch_one(
            "SELECT * FROM providers WHERE id = ?", (provider_id,)
        )
        return self._row_to_provider(row) if row else None

    def save_provider(
        self, payload: dict[str, Any], provider_id: str | None = None
    ) -> dict[str, Any]:
        normalized = self._normalize_provider_payload(payload, provider_id)
        now = now_iso()
        existing = self._state.fetch_one(
            "SELECT * FROM providers WHERE id = ?", (normalized["id"],)
        )

        if existing is None:
            self._state.execute(
                """
                INSERT INTO providers (
                    id, name, provider_type, enabled, default_model, api_base, api_version,
                    organization, secret_mode, secret_env_var, revision, last_test_status,
                    last_test_error, last_tested_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized["id"],
                    normalized["name"],
                    normalized["providerType"],
                    int(normalized["enabled"]),
                    normalized["defaultModel"],
                    normalized["apiBase"],
                    normalized["apiVersion"],
                    normalized["organization"],
                    normalized["secretMode"],
                    normalized["secretEnvVar"],
                    1,
                    "unknown",
                    None,
                    None,
                    now,
                    now,
                ),
            )
        else:
            self._state.execute(
                """
                UPDATE providers
                SET name = ?, provider_type = ?, enabled = ?, default_model = ?, api_base = ?, api_version = ?,
                    organization = ?, secret_mode = ?, secret_env_var = ?, revision = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    normalized["name"],
                    normalized["providerType"],
                    int(normalized["enabled"]),
                    normalized["defaultModel"],
                    normalized["apiBase"],
                    normalized["apiVersion"],
                    normalized["organization"],
                    normalized["secretMode"],
                    normalized["secretEnvVar"],
                    int(existing["revision"]) + 1,
                    now,
                    normalized["id"],
                ),
            )

        session_secret = str(payload.get("sessionSecret") or "").strip()
        if normalized["secretMode"] == "session":
            if session_secret:
                self._session_secrets[normalized["id"]] = session_secret
            elif payload.get("clearSessionSecret"):
                self._session_secrets.pop(normalized["id"], None)
        else:
            self._session_secrets.pop(normalized["id"], None)

        saved = self.get_provider(normalized["id"])
        if saved is None:
            raise RuntimeError(
                "provider save succeeded but the provider could not be reloaded"
            )
        return saved

    def delete_provider(self, provider_id: str) -> None:
        self._state.execute("DELETE FROM providers WHERE id = ?", (provider_id,))
        self._session_secrets.pop(provider_id, None)

    def test_provider(self, provider_id: str) -> dict[str, Any]:
        provider = self._require_provider(provider_id)
        now = now_iso()

        try:
            if provider["providerType"] == "mock":
                preview = "MOCK OK"
            else:
                lm = self.build_lm(provider_id)
                outputs = lm("Reply with exactly OK.")
                preview = self._extract_text_output(outputs)
            status = "ok"
            error_message = None
        except Exception as exc:  # pragma: no cover - runtime path
            preview = None
            status = "error"
            error_message = str(exc)

        self._state.execute(
            "UPDATE providers SET last_test_status = ?, last_test_error = ?, last_tested_at = ? WHERE id = ?",
            (status, error_message, now, provider_id),
        )

        saved = self._require_provider(provider_id)
        return {
            "provider": saved,
            "status": status,
            "preview": preview,
            "error": error_message,
            "testedAt": now,
        }

    def build_lm(
        self,
        provider_id: str,
        *,
        model_override: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Any:
        provider = self._require_provider(provider_id)
        if provider["providerType"] == "mock":
            return _create_mock_dspy_lm(
                provider.get("defaultModel") or "mock/echo-agent"
            )

        try:
            dspy = importlib.import_module("dspy")
        except ModuleNotFoundError as exc:  # pragma: no cover - depends on local env
            raise RuntimeError(
                "DSPy is required to build language-model clients. Install the control-plane dependencies first."
            ) from exc

        secret = self._resolve_secret(provider)
        model = (model_override or provider.get("defaultModel") or "").strip()
        if not model:
            raise ValueError("provider is missing a default model")

        kwargs: dict[str, Any] = {
            "model": model,
            "temperature": temperature if temperature is not None else 0.2,
            "max_tokens": max_tokens if max_tokens is not None else 700,
            "cache": False,
            "num_retries": 2,
        }
        if provider.get("apiBase"):
            kwargs["api_base"] = provider["apiBase"]
        if provider.get("apiVersion"):
            kwargs["api_version"] = provider["apiVersion"]
        if provider.get("organization"):
            kwargs["organization"] = provider["organization"]
        if secret is not None:
            kwargs["api_key"] = secret
        return dspy.LM(**kwargs)

    def delete_session_secret(self, provider_id: str) -> dict[str, Any]:
        self._session_secrets.pop(provider_id, None)
        provider = self._require_provider(provider_id)
        if provider["secretMode"] == "session":
            self._state.execute(
                "UPDATE providers SET last_test_status = ?, last_test_error = ? WHERE id = ?",
                ("unknown", None, provider_id),
            )
        updated = self._require_provider(provider_id)
        return updated

    def _normalize_provider_payload(
        self,
        payload: dict[str, Any],
        provider_id: str | None,
    ) -> dict[str, Any]:
        provider_type = str(
            payload.get("providerType") or payload.get("provider_type") or ""
        ).strip()
        if provider_type not in PROVIDER_TYPES:
            raise ValueError(f"unsupported provider type: {provider_type or '<empty>'}")
        spec = PROVIDER_TYPES[provider_type]

        provider_name = str(payload.get("name") or "").strip()
        if len(provider_name) < 2:
            raise ValueError("provider name must be at least 2 characters")

        secret_mode = str(
            payload.get("secretMode") or payload.get("secret_mode") or "none"
        ).strip()
        if secret_mode not in spec.secret_modes:
            raise ValueError(
                f"provider type `{provider_type}` supports secret modes: {', '.join(spec.secret_modes)}"
            )

        default_model = str(
            payload.get("defaultModel")
            or payload.get("default_model")
            or spec.default_model
        ).strip()
        if not default_model:
            raise ValueError("provider defaultModel is required")

        api_base = self._clean_optional_string(
            payload.get("apiBase") or payload.get("api_base")
        )
        api_version = self._clean_optional_string(
            payload.get("apiVersion") or payload.get("api_version")
        )
        organization = self._clean_optional_string(payload.get("organization"))
        secret_env_var = self._clean_optional_string(
            payload.get("secretEnvVar") or payload.get("secret_env_var")
        )

        if secret_mode == "env" and not secret_env_var:
            raise ValueError("secretEnvVar is required when secretMode is `env`")
        if (
            secret_mode == "session"
            and not str(payload.get("sessionSecret") or "").strip()
            and provider_id is None
        ):
            raise ValueError(
                "sessionSecret is required for new providers using session secret mode"
            )
        if api_base and api_base.startswith("http://") and not spec.local_only_http:
            raise ValueError("remote provider apiBase values must use https://")
        if (
            spec.local_only_http
            and api_base
            and not re.match(r"^http://(127\.0\.0\.1|localhost)(:\d+)?$", api_base)
        ):
            raise ValueError(
                "Ollama apiBase must point at a loopback http://127.0.0.1 or http://localhost address"
            )

        return {
            "id": provider_id or str(uuid.uuid4()),
            "name": provider_name,
            "providerType": provider_type,
            "enabled": bool(payload.get("enabled", True)),
            "defaultModel": default_model,
            "apiBase": api_base,
            "apiVersion": api_version,
            "organization": organization,
            "secretMode": secret_mode,
            "secretEnvVar": secret_env_var,
        }

    def _require_provider(self, provider_id: str) -> dict[str, Any]:
        provider = self.get_provider(provider_id)
        if provider is None:
            raise KeyError(f"provider `{provider_id}` was not found")
        return provider

    def _resolve_secret(self, provider: dict[str, Any]) -> str | None:
        secret_mode = provider["secretMode"]
        if secret_mode == "none":
            return None
        if secret_mode == "env":
            env_var = provider.get("secretEnvVar") or ""
            secret = __import__("os").environ.get(env_var)
            if not secret:
                raise RuntimeError(
                    f"environment variable `{env_var}` is not set for provider `{provider['name']}`"
                )
            return secret
        if secret_mode == "session":
            secret = self._session_secrets.get(provider["id"])
            if not secret:
                raise RuntimeError(
                    f"provider `{provider['name']}` requires a session secret before it can be used"
                )
            return secret
        raise RuntimeError(f"unsupported secret mode `{secret_mode}`")

    def _row_to_provider(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        secret_mode = row["secret_mode"]
        has_secret = False
        if secret_mode == "none":
            has_secret = True
        elif secret_mode == "env":
            env_var = row.get("secret_env_var")
            has_secret = bool(env_var and __import__("os").environ.get(env_var))
        elif secret_mode == "session":
            has_secret = row["id"] in self._session_secrets

        return {
            "id": row["id"],
            "name": row["name"],
            "providerType": row["provider_type"],
            "enabled": bool(row["enabled"]),
            "defaultModel": row["default_model"],
            "apiBase": row["api_base"],
            "apiVersion": row["api_version"],
            "organization": row["organization"],
            "secretMode": secret_mode,
            "secretEnvVar": row["secret_env_var"],
            "hasSecret": has_secret,
            "revision": int(row["revision"]),
            "lastTestStatus": row["last_test_status"],
            "lastTestError": row["last_test_error"],
            "lastTestedAt": row["last_tested_at"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def _extract_text_output(self, outputs: Any) -> str:
        if isinstance(outputs, list) and outputs:
            first = outputs[0]
            if isinstance(first, str):
                return first
            if isinstance(first, dict):
                return str(first.get("text") or first)
        return str(outputs)

    def _clean_optional_string(self, value: Any) -> str | None:
        text = str(value).strip() if value is not None else ""
        return text or None


_OUTPUT_FIELD_PATTERN = re.compile(
    r"Return the final answer in the `([a-zA-Z][a-zA-Z0-9_]*)` field\."
)
_DSPY_FIELD_MARKER_PATTERN = re.compile(
    r"\[\[\s*##\s*([a-zA-Z][a-zA-Z0-9_]*)\s*##\s*\]\]"
)
_JSON_GUIDANCE_PATTERN = re.compile(r"JSON shape guidance:\s*(\{.*?\})", re.S)


def _extract_mock_output_field_name(prompt_text: str) -> str:
    match = _OUTPUT_FIELD_PATTERN.search(prompt_text)
    if match:
        return match.group(1)

    markers = [
        marker
        for marker in _DSPY_FIELD_MARKER_PATTERN.findall(prompt_text)
        if marker not in {"request", "reasoning"}
    ]
    if markers:
        return markers[-1]

    return "response"


def _extract_mock_json_shape(prompt_text: str) -> dict[str, Any] | None:
    match = _JSON_GUIDANCE_PATTERN.search(prompt_text)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _materialize_mock_json_shape(shape: Any, *, field_name: str) -> Any:
    if isinstance(shape, dict):
        if not shape:
            return {field_name: f"Mock {field_name}"}
        return {
            str(key): _materialize_mock_json_shape(value, field_name=str(key))
            for key, value in shape.items()
        }
    if isinstance(shape, list):
        if not shape:
            return [f"Mock {field_name} item"]
        return [_materialize_mock_json_shape(shape[0], field_name=field_name)]
    if isinstance(shape, str):
        normalized = shape.strip().lower()
        if normalized in {"number", "float", "int", "integer"}:
            return 1
        if normalized in {"boolean", "bool"}:
            return True
        if normalized in {"array", "list"}:
            return [f"Mock {field_name} item"]
        if normalized in {"object", "json"}:
            return {field_name: f"Mock {field_name}"}
        return f"Mock {field_name}"
    if isinstance(shape, bool):
        return shape
    if isinstance(shape, (int, float)):
        return shape
    return f"Mock {field_name}"


def _create_mock_dspy_lm(model: str) -> Any:
    try:
        dspy = importlib.import_module("dspy")
        base_class = dspy.BaseLM
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on local env
        raise RuntimeError(
            "DSPy is required for the mock LM provider because agent execution is DSPy-driven."
        ) from exc

    class MockDSPyLM(base_class):
        def __init__(self, model_name: str) -> None:
            super().__init__(
                model=model_name,
                model_type="chat",
                temperature=0.0,
                max_tokens=512,
                cache=False,
            )

        def forward(
            self,
            prompt: str | None = None,
            messages: list[dict[str, Any]] | None = None,
            **kwargs: Any,
        ):
            transcript = messages or []
            user_message = transcript[-1]["content"] if transcript else (prompt or "")
            user_message = str(user_message)
            output_field_name = _extract_mock_output_field_name(user_message)
            reasoning_text = (
                "Mock provider produced a deterministic local response for smoke tests."
            )
            response_text = (
                "Mock provider reply from VLoop. This proves the DSPy pipeline is working locally. "
                f"Input excerpt: {user_message[:220]}"
            )
            json_shape = _extract_mock_json_shape(user_message)
            if json_shape is not None:
                output_value = _materialize_mock_json_shape(
                    json_shape,
                    field_name=output_field_name,
                )
            else:
                output_value = response_text
            payload = json.dumps(
                {
                    "reasoning": reasoning_text,
                    output_field_name: output_value,
                },
                ensure_ascii=False,
            )
            message = SimpleNamespace(
                content=payload,
                reasoning_content=reasoning_text,
            )
            choice = SimpleNamespace(message=message)
            return SimpleNamespace(
                choices=[choice],
                usage={
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                },
                _hidden_params={},
                model=self.model,
            )

    return MockDSPyLM(model)
