"""Simple URL router that dispatches to handler registrations in order.

Key design:
- Static segments are matched literally (e.g. ``"api"``).
- The magic sentinel ``"*"`` matches exactly one path segment of any value.
- ``"**"`` as the last segment matches *zero-or-more* trailing segments
  (greedy; useful for catch-all patterns when needed).

Each registered handler receives ``(handler, method, path, query, body, runtime)``
and is expected to call `write_json` / `write_error_json` on the first argument
(the HTTP-handler *self*).  Return values from handlers are ignored.

Example registrations::

    register("GET",  ("health",),             handle_health)
    register("*",    ("api","v1","agents","*"), handle_agent_singleton)
    register("*",    ("api","v1","agents","*","*"), handle_agent_action)
"""

from __future__ import annotations

from typing import Any, Callable

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

Handler = Callable[..., Any]
HandlerEntry = tuple[str, tuple[str | type, ...], Handler]

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_registry: list[HandlerEntry] = []


def register(
    method: str,
    pattern: tuple[str, ...],
    handler: Handler,
) -> None:
    """Add a pattern → handler mapping.

    ``"*"`` inside *pattern* matches any single path segment.
    ``"**"`` at the end matches zero or more remaining segments.
    """
    converted: tuple[str | type, ...] = tuple(
        _sentinel_star if seg in ("*", "__id__", "__action__") else seg
        for seg in pattern
    )
    _registry.append((method, converted, handler))


# ---------------------------------------------------------------------------
# Sentinel values for wildcard matching
# ---------------------------------------------------------------------------


class _Star:
    """Matches exactly one segment of any value."""

    def __repr__(self) -> str:
        return "*"


class _DoubleStar:
    """Matches zero or more trailing segments."""

    def __repr__(self) -> str:
        return "**"


_sentinel_star: Any = _Star()
_sentinel_double_star: Any = _DoubleStar()


# ---------------------------------------------------------------------------
# Public dispatch
# ---------------------------------------------------------------------------


def route(
    http_handler: Any,
    method: str,
    path: str,
    query: dict[str, list[str]],
    body: dict[str, Any],
    runtime: Any,
) -> Any:
    """Walk the registration list; return the first match or raise KeyError."""
    from cp.http_utils import split_segments

    segments = split_segments(path)

    for meth, pattern, handler_fn in _registry:
        if meth != "*" and meth != method:
            continue
        if _match(pattern, segments):
            return handler_fn(http_handler, method, path, query, body, runtime)

    raise KeyError(f"route `{path}` was not found")


# ---------------------------------------------------------------------------
# Matching helpers
# ---------------------------------------------------------------------------


def _match(pattern: tuple[Any, ...], segments: list[str]) -> bool:
    """Check whether *pattern* matches *segments*."""
    pi = 0
    si = 0
    plen = len(pattern)
    slen = len(segments)

    while pi < plen and si < slen:
        p = pattern[pi]
        if p is _sentinel_double_star:
            # Double-star only valid as the last element.
            return True

        if p is _sentinel_star:
            # Consume one segment from both sides.
            pi += 1
            si += 1
            continue

        # Literal match
        if p != segments[si]:
            return False
        pi += 1
        si += 1

    # If we exhausted pattern but there are leftover segments → no match
    if pi < plen:
        # Check if remaining pattern is only "**"
        return all(p is _sentinel_double_star for p in pattern[pi:])

    # Must have consumed exactly all segments
    return si == slen
