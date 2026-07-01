"""Memory routes: list, create, and delete bounded persistent memory entries.

Exposes the Control_Plane API over the Memory_Store (`core/memory_store.py`):

* ``GET    /api/v1/memory``      — list current Memory_Entries (Requirement 11.4),
  optionally filtered by ``?category=``.
* ``POST   /api/v1/memory``      — record a new Memory_Entry (Requirement 11.1).
* ``DELETE /api/v1/memory/{id}`` — remove a Memory_Entry from persistence
  (Requirement 11.3).

Following the handler conventions in ``cp/handlers/agents.py`` and
``cp/handlers/providers.py``, each handler receives
``(handler, method, path, query, body, runtime)`` and writes its response via
``write_json``. The Memory_Store is reached only through the documented runtime
accessors (``runtime.list_memory_entries`` / ``runtime.record_memory_entry`` /
``runtime.delete_memory_entry``); this module never touches the store directly.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any
from urllib.parse import unquote

from cp.handlers.router import register
from cp.http_responders import write_json
from cp.http_utils import (
    optional_query_value,
    require_method,
    required_string,
    split_segments,
)

# ---------------------------------------------------------------------------
# Collection  /api/v1/memory
# ---------------------------------------------------------------------------


def _handle_memory(
    handler: Any, method: str, _path: str, query: Any, body: Any, runtime: Any
) -> None:
    if method == "GET":
        # Requirement 11.4 — list all current entries (optionally by category).
        category = optional_query_value(query, "category")
        entries = runtime.list_memory_entries(category)
        write_json(handler, {"memoryEntries": entries})
    elif method == "POST":
        # Requirement 11.1 — persist a new entry so it survives across sessions.
        content = required_string(body, "content")
        category = _optional_body_value(body, "category")
        if category is None:
            entry = runtime.record_memory_entry(content)
        else:
            entry = runtime.record_memory_entry(content, category)
        write_json(handler, {"memoryEntry": entry}, status=HTTPStatus.CREATED)
    else:
        require_method(method, {"GET", "POST"})


# ---------------------------------------------------------------------------
# Singleton  /api/v1/memory/{id}
# ---------------------------------------------------------------------------


def _handle_memory_entry(
    handler: Any, method: str, _path: str, _query: Any, _body: Any, runtime: Any
) -> None:
    segments = split_segments(_path)
    entry_id = unquote(segments[3])

    if method == "DELETE":
        # Requirement 11.3 — remove from persistence; a descriptive error is
        # surfaced by the Memory_Store if the deletion cannot be completed.
        runtime.delete_memory_entry(entry_id)
        write_json(handler, {"ok": True, "memoryId": entry_id})
    else:
        require_method(method, {"DELETE"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _optional_body_value(payload: dict[str, Any], *names: str) -> str | None:
    """Return the first non-empty string field from *payload*, else ``None``."""
    for name in names:
        value = payload.get(name)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


# -- registration ------------------------------------------------------------

register("*", ("api", "v1", "memory"), _handle_memory)
register("*", ("api", "v1", "memory", "*"), _handle_memory_entry)
