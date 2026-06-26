"""Provider service — CRUD, LM building, secret management, and test."""

from __future__ import annotations

import importlib
import re
import uuid
from typing import TYPE_CHECKING, Any

from core.mock_dspy_lm import create_mock_dspy_lm

from core.helpers import now_iso
from core.provider_types import PROVIDER_TYPES

if TYPE_CHECKING:
    from core.database import DatabaseBackend


class ProviderService:
    """Manages provider configuration, LM construction, and secret lifecycle."""

    def __init__(self, state: DatabaseBackend) -> None:
        self._state = state
        self._session_secrets: dict[str, str] = {}

    # -- catalog / CRUD -----------------------------------------------------

    def provider_catalog(self) -> list[dict[str, Any]]:
        return [spec.to_dict() for spec in PROVIDER_TYPES.values()]

    def list_providers(self) -> list[dict[str, Any]]:
        rows = self._state.fetch_all(
            "SELECT * FROM providers ORDER BY updated_at DESC, name ASC"
        )
        providers: list[dict[str, Any]] = []
        for row in rows:
            provider = _row_to_provider(row, self._session_secrets)
            if provider is not None:
                providers.append(provider)
        return providers

    def get_provider(self, provider_id: str) -> dict[str, Any] | None:
        row = self._state.fetch_one(
            "SELECT * FROM providers WHERE id = ?", (provider_id,)
        )
        return _row_to_provider(row, self._session_secrets) if row else None

    def save_provider(
        self, payload: dict[str, Any], provider_id: str | None = None
    ) -> dict[str, Any]:
        normalized = _normalize_provider_payload(payload, provider_id)
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

    # -- test / build --------------------------------------------------------

    def test_provider(self, provider_id: str) -> dict[str, Any]:
        provider = _require_provider(self, provider_id)
        now = now_iso()

        try:
            if provider["providerType"] == "mock":
                preview = "MOCK OK"
            else:
                lm = self.build_lm(provider_id)
                outputs = lm("Reply with exactly OK.")
                preview = _extract_text_output(outputs)
            status = "ok"
            error_message = None
        except Exception as exc:
            preview = None
            status = "error"
            error_message = str(exc)

        self._state.execute(
            "UPDATE providers SET last_test_status = ?, last_test_error = ?, last_tested_at = ? WHERE id = ?",
            (status, error_message, now, provider_id),
        )

        saved = _require_provider(self, provider_id)
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
        provider = _require_provider(self, provider_id)
        if provider["providerType"] == "mock":
            return create_mock_dspy_lm(
                provider.get("defaultModel") or "mock/echo-agent"
            )

        try:
            dspy = importlib.import_module("dspy")
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "DSPy is required to build language-model clients. Install the control-plane dependencies first."
            ) from exc

        secret = _resolve_secret(provider, self._session_secrets)
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

    # -- secrets -------------------------------------------------------------

    def delete_session_secret(self, provider_id: str) -> dict[str, Any]:
        self._session_secrets.pop(provider_id, None)
        provider = _require_provider(self, provider_id)
        if provider["secretMode"] == "session":
            self._state.execute(
                "UPDATE providers SET last_test_status = ?, last_test_error = ? WHERE id = ?",
                ("unknown", None, provider_id),
            )
        updated = _require_provider(self, provider_id)
        return updated


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _normalize_provider_payload(
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

    api_base = _clean_optional_string(payload.get("apiBase") or payload.get("api_base"))
    api_version = _clean_optional_string(
        payload.get("apiVersion") or payload.get("api_version")
    )
    organization = _clean_optional_string(payload.get("organization"))
    secret_env_var = _clean_optional_string(
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


def _require_provider(service: ProviderService, provider_id: str) -> dict[str, Any]:
    provider = service.get_provider(provider_id)
    if provider is None:
        raise KeyError(f"provider `{provider_id}` was not found")
    return provider


def _resolve_secret(
    provider: dict[str, Any], session_secrets: dict[str, str]
) -> str | None:
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
        secret = session_secrets.get(provider["id"])
        if not secret:
            raise RuntimeError(
                f"provider `{provider['name']}` requires a session secret before it can be used"
            )
        return secret
    raise RuntimeError(f"unsupported secret mode `{secret_mode}`")


def _row_to_provider(
    row: dict[str, Any] | None,
    session_secrets: dict[str, str],
) -> dict[str, Any] | None:
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
        has_secret = row["id"] in session_secrets

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


def _extract_text_output(outputs: Any) -> str:
    if isinstance(outputs, list) and outputs:
        first = outputs[0]
        if isinstance(first, str):
            return first
        if isinstance(first, dict):
            return str(first.get("text") or first)
    return str(outputs)


def _clean_optional_string(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None
