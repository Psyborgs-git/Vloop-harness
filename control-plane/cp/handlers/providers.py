"""Provider routes: CRUD, catalog, test, and secret management."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any
from urllib.parse import unquote

from cp.handlers.router import register
from cp.http_responders import write_json
from cp.http_utils import require_method, required_string, split_segments

# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


def _handle_catalog(
    handler: Any, method: str, _path: str, _query: Any, _body: Any, runtime: Any
) -> None:
    """GET /api/v1/catalog/provider-types (and aliases)."""
    require_method(method, {"GET"})
    write_json(handler, {"providerCatalog": runtime.provider_catalog()})


# ---------------------------------------------------------------------------
# Collection  /api/v1/providers
# ---------------------------------------------------------------------------


def _handle_providers(
    handler: Any, method: str, _path: str, _query: Any, body: Any, runtime: Any
) -> None:
    if method == "GET":
        write_json(handler, {"providers": runtime.list_providers()})
    elif method == "POST":
        provider = runtime.save_provider(body)
        write_json(handler, {"provider": provider}, status=HTTPStatus.CREATED)
    else:
        require_method(method, {"GET", "POST"})


# ---------------------------------------------------------------------------
# Singleton  /api/v1/providers/{id}
# ---------------------------------------------------------------------------


def _handle_provider(
    handler: Any, method: str, _path: str, _query: Any, body: Any, runtime: Any
) -> None:
    segments = split_segments(_path)
    provider_id = unquote(segments[3])

    if method == "GET":
        provider = runtime.get_provider(provider_id)
        if provider is None:
            raise KeyError(f"provider `{provider_id}` was not found")
        write_json(handler, {"provider": provider})
    elif method in {"PUT", "PATCH", "POST"}:
        provider = runtime.save_provider(body, provider_id)
        write_json(handler, {"provider": provider})
    elif method == "DELETE":
        runtime.delete_provider(provider_id)
        write_json(handler, {"ok": True, "providerId": provider_id})
    else:
        require_method(method, {"GET", "PUT", "PATCH", "POST", "DELETE"})


# ---------------------------------------------------------------------------
# Sub-resources  /api/v1/providers/{id}/{action}
# ---------------------------------------------------------------------------


def _handle_provider_action(
    handler: Any, method: str, _path: str, _query: Any, body: Any, runtime: Any
) -> None:
    segments = split_segments(_path)
    provider_id = unquote(segments[3])
    suffix = segments[4]

    if suffix == "test":
        require_method(method, {"POST"})
        write_json(handler, runtime.test_provider(provider_id))
    elif suffix == "secret":
        require_method(method, {"DELETE"})
        provider = runtime.delete_session_secret(provider_id)
        write_json(handler, {"provider": provider})
    else:
        raise KeyError(f"provider action `{suffix}` is not supported")


def _handle_provider_test(
    handler: Any, method: str, _path: str, _query: Any, body: Any, runtime: Any
) -> None:
    """POST /api/v1/providers/test  (test by payload, not URL id)."""
    require_method(method, {"POST"})
    provider_id = required_string(body, "providerId", "provider_id")
    write_json(handler, runtime.test_provider(provider_id))


# -- registration ------------------------------------------------------------

_CATALOG_PATTERNS = [
    ("api", "v1", "catalog", "provider-types"),
    ("api", "v1", "providers", "catalog"),
    ("api", "v1", "provider-catalog"),
    ("api", "v1", "catalog", "providers"),
]

for pat in _CATALOG_PATTERNS:
    register("*", pat, _handle_catalog)

register("*", ("api", "v1", "providers"), _handle_providers)
register("*", ("api", "v1", "providers", "test"), _handle_provider_test)
register("*", ("api", "v1", "providers", "*"), _handle_provider)
register("*", ("api", "v1", "providers", "*", "*"), _handle_provider_action)
