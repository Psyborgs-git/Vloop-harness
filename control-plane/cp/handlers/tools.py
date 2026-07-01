"""Tool/Toolset routes: list, enable, and disable per scope (Requirement 9).

Exposes the Control_Plane API over the Tool_Registry
(:mod:`core.tool_registry`), which catalogs Tools and the Toolsets that group
them and gates which are available in a given scope:

* ``GET  /api/v1/tools``                  — list catalogued Tools, optionally
  resolved for a ``?scope=`` identifier (Requirement 9.1).
* ``POST /api/v1/tools/{name}/enable``    — enable a single Tool's toolset in a
  scope (Requirement 9.2).
* ``POST /api/v1/tools/{name}/disable``   — disable a single Tool's toolset in a
  scope (Requirement 9.2).
* ``GET  /api/v1/toolsets``               — list catalogued Toolsets, optionally
  resolved for a ``?scope=`` identifier (Requirement 9.1).
* ``POST /api/v1/toolsets/{id}/enable``   — enable a Toolset in a scope
  (Requirement 9.2).
* ``POST /api/v1/toolsets/{id}/disable``  — disable a Toolset in a scope
  (Requirement 9.2).

Following the handler conventions in :mod:`cp.handlers.agents` and
:mod:`cp.handlers.schedules`, each handler receives
``(handler, method, path, query, body, runtime)``, validates the method with
:func:`~cp.http_utils.require_method`, and writes its response via
:func:`~cp.http_responders.write_json`. Invalid input raises ``ValueError``
(mapped to ``400`` by the HTTP shell); unknown Tools/Toolsets raise ``KeyError``
(mapped to ``404``).

Runtime accessor contract (wired in task 30.10 — this module never touches the
Tool_Registry directly):

* ``runtime.list_tools(scope=<str | None>) -> list[dict]``
      Return the catalogued Tools. When ``scope`` is provided, each entry is
      resolved for that scope (for example, carrying an ``enabled`` flag for the
      scope); when ``scope`` is ``None`` the catalog is returned without scope
      resolution.
* ``runtime.list_toolsets(scope=<str | None>) -> list[dict]``
      As above, for the Toolsets that group Tools.
* ``runtime.set_tool_enabled(tool_name: str, scope: str, enabled: bool) -> dict``
      Enable (``enabled=True``) or disable (``enabled=False``) the Tool's
      toolset within ``scope`` and return the updated Tool view. Raises
      ``KeyError`` when ``tool_name`` is not catalogued.
* ``runtime.set_toolset_enabled(toolset_id: str, scope: str, enabled: bool) -> dict``
      Enable or disable the Toolset within ``scope`` and return the updated
      Toolset view. Raises ``KeyError`` when ``toolset_id`` is not catalogued.

For the enable/disable operations ``scope`` is a required scope identifier
string supplied in the request body; for the listing operations it is an
optional ``scope`` query parameter.
"""

from __future__ import annotations

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

# Sub-resource actions that toggle scope enablement (Requirement 9.2).
_ACTION_ENABLE = "enable"
_ACTION_DISABLE = "disable"
_VALID_ACTIONS = frozenset({_ACTION_ENABLE, _ACTION_DISABLE})


# ---------------------------------------------------------------------------
# Tools collection  /api/v1/tools
# ---------------------------------------------------------------------------


def _handle_tools(
    handler: Any, method: str, _path: str, query: Any, _body: Any, runtime: Any
) -> None:
    """GET lists catalogued Tools, optionally resolved per scope (Req 9.1)."""
    require_method(method, {"GET"})
    scope = optional_query_value(query, "scope")
    write_json(handler, {"tools": runtime.list_tools(scope=scope)})


# ---------------------------------------------------------------------------
# Tool sub-resource  /api/v1/tools/{name}/{action}
# ---------------------------------------------------------------------------


def _handle_tool_action(
    handler: Any, method: str, _path: str, _query: Any, body: Any, runtime: Any
) -> None:
    """POST /{name}/enable and /{name}/disable toggle a Tool per scope (Req 9.2)."""
    segments = split_segments(_path)
    tool_name = unquote(segments[3])
    action = segments[4]

    enabled = _coerce_action(action)
    require_method(method, {"POST"})
    scope = required_string(body, "scope")
    tool = runtime.set_tool_enabled(tool_name, scope, enabled)
    write_json(handler, {"tool": tool})


# ---------------------------------------------------------------------------
# Toolsets collection  /api/v1/toolsets
# ---------------------------------------------------------------------------


def _handle_toolsets(
    handler: Any, method: str, _path: str, query: Any, _body: Any, runtime: Any
) -> None:
    """GET lists catalogued Toolsets, optionally resolved per scope (Req 9.1)."""
    require_method(method, {"GET"})
    scope = optional_query_value(query, "scope")
    write_json(handler, {"toolsets": runtime.list_toolsets(scope=scope)})


# ---------------------------------------------------------------------------
# Toolset sub-resource  /api/v1/toolsets/{id}/{action}
# ---------------------------------------------------------------------------


def _handle_toolset_action(
    handler: Any, method: str, _path: str, _query: Any, body: Any, runtime: Any
) -> None:
    """POST /{id}/enable and /{id}/disable toggle a Toolset per scope (Req 9.2)."""
    segments = split_segments(_path)
    toolset_id = unquote(segments[3])
    action = segments[4]

    enabled = _coerce_action(action)
    require_method(method, {"POST"})
    scope = required_string(body, "scope")
    toolset = runtime.set_toolset_enabled(toolset_id, scope, enabled)
    write_json(handler, {"toolset": toolset})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _coerce_action(action: str) -> bool:
    """Map an ``enable``/``disable`` path segment to an ``enabled`` boolean.

    Any other action is an unknown sub-resource and raises ``KeyError`` (→ 404).
    """
    if action not in _VALID_ACTIONS:
        raise KeyError(f"tool action `{action}` is not supported")
    return action == _ACTION_ENABLE


# -- registration ------------------------------------------------------------

register("*", ("api", "v1", "tools"), _handle_tools)
register("*", ("api", "v1", "tools", "*", "*"), _handle_tool_action)
register("*", ("api", "v1", "toolsets"), _handle_toolsets)
register("*", ("api", "v1", "toolsets", "*", "*"), _handle_toolset_action)
