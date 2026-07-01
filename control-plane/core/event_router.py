"""Event_Router — normalize, attribute, redact, and persist workflow events.

The Event_Router is the Control_Plane subsystem that converts Kernel events and
internal orchestration events into a single stream of user-facing *workflow
events*. Every event it emits:

* is normalized into the canonical :class:`WorkflowEvent` shape;
* is attributed to a single ``Workflow_Run`` id (Requirement 21.5) — events that
  cannot be attributed to a run are not workflow events and are dropped;
* has its payload scrubbed of secret values before it ever leaves the process
  (Requirement 21.4); and
* is persisted to the ``workflow_events`` table with a per-run monotonic ``seq``
  (Requirement 4.1, restart-survivable history).

Persistence uses the existing :class:`~core.database.DatabaseBackend` and
``core.helpers.to_json`` for the JSON payload column, matching the schema in
``core/database.py``::

    workflow_events(run_id, seq, type, step_id, message, payload_json, created_at)

A lightweight subscriber hook is provided so the (separately-built) WebSocket
server can stream emitted events to the Frontend without the Event_Router
depending on the transport layer.

Security note: ``GrantContext`` and other grant references carry only a grant
id / session reference and are therefore safe to include in payloads; raw secret
values must never enter Control_Plane state in the first place. Redaction here is
defense-in-depth so that any secret that does slip into a payload (for example an
``api_key`` field copied from a provider config) never reaches a log, the
database, or the Frontend.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

from core.database import DatabaseBackend
from core.helpers import from_json, now_iso, to_json

LOGGER = logging.getLogger("vloop.control_plane.event_router")

# The placeholder substituted in place of any redacted secret value.
REDACTED = "[REDACTED]"

# Substrings that, when found (case-insensitively) in a payload key, mark that
# key's value as a secret to be redacted. Kept intentionally broad: over-redacting
# a non-secret is harmless, leaking a secret is not.
_SENSITIVE_KEY_SUBSTRINGS: tuple[str, ...] = (
    "secret",
    "password",
    "passwd",
    "token",
    "api_key",
    "apikey",
    "api-key",
    "access_key",
    "secret_key",
    "private_key",
    "client_secret",
    "credential",
    "authorization",
    "bearer",
)

# Grant-reference keys are explicitly *not* secrets: they reference a Kernel
# secret grant by id/session only (Requirements 6.5, 16.4, 18.4) and must remain
# visible for auditing and run attribution.
_GRANT_REFERENCE_KEYS: frozenset[str] = frozenset(
    {"grant_id", "session_ref", "grant_ref", "kernel_snapshot_ref"}
)


# ---------------------------------------------------------------------------
# Canonical user-facing event types
# ---------------------------------------------------------------------------


class WorkflowEventType:
    """Canonical, user-facing workflow event type names.

    Internal orchestration events and Kernel events are normalized onto these
    types so the Frontend sees one stable vocabulary regardless of source.
    """

    RUN_CREATED = "run.created"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    RUN_CANCELLED = "run.cancelled"
    RUN_REJECTED = "run.rejected"
    RUN_BUDGET_EXCEEDED = "run.budget_exceeded"
    STEP_STATE_CHANGED = "step.state_changed"
    TOOL_DENIED = "tool.denied"
    APPROVAL_REQUIRED = "approval.required"
    BUDGET_STATUS = "budget.status"
    RATE_LIMIT_STATUS = "rate_limit.status"
    MCP_CONNECTED = "mcp.connected"
    MCP_DISCONNECTED = "mcp.disconnected"
    KERNEL_EVENT = "kernel.event"


@dataclass(slots=True)
class WorkflowEvent:
    """A normalized, secret-redacted, run-attributed workflow event.

    Mirrors the ``workflow_events`` table columns. ``payload`` is always already
    redacted by the time an instance exists.
    """

    run_id: str
    seq: int
    type: str
    message: str
    step_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "seq": self.seq,
            "type": self.type,
            "step_id": self.step_id,
            "message": self.message,
            "payload": self.payload,
            "created_at": self.created_at,
        }


# ---------------------------------------------------------------------------
# Secret redaction
# ---------------------------------------------------------------------------


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    if lowered in _GRANT_REFERENCE_KEYS:
        return False
    return any(token in lowered for token in _SENSITIVE_KEY_SUBSTRINGS)


def redact_secrets(value: Any, known_secrets: tuple[str, ...] = ()) -> Any:
    """Return a deep copy of *value* with secret values redacted.

    Two complementary strategies are applied (Requirement 21.4):

    * **Key-based**: any mapping value whose key looks like a secret (for example
      ``api_key``, ``authorization``, ``password``) is replaced wholesale with
      :data:`REDACTED`.
    * **Value-based**: any occurrence of a registered known secret string is
      scrubbed wherever it appears, including as a substring inside a larger
      string. This catches secrets that land under an innocuous key.

    The input is never mutated; nested dicts and lists are copied. Non-container
    leaf values are returned scrubbed of any known-secret substrings.
    """
    secrets = tuple(s for s in known_secrets if s)

    if isinstance(value, dict):
        result: dict[Any, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and _is_sensitive_key(key):
                result[key] = REDACTED
            else:
                result[key] = redact_secrets(item, secrets)
        return result

    if isinstance(value, (list, tuple)):
        return [redact_secrets(item, secrets) for item in value]

    if isinstance(value, str):
        return _scrub_known_secrets(value, secrets)

    return value


def _scrub_known_secrets(text: str, secrets: tuple[str, ...]) -> str:
    scrubbed = text
    for secret in secrets:
        if secret and secret in scrubbed:
            scrubbed = scrubbed.replace(secret, REDACTED)
    return scrubbed


# ---------------------------------------------------------------------------
# Event_Router
# ---------------------------------------------------------------------------


class EventRouter:
    """Normalizes, redacts, attributes, persists, and fans out workflow events.

    Thread-safe: a single lock serializes sequence assignment and persistence so
    concurrent steps of a run cannot collide on the per-run ``seq``.
    """

    def __init__(self, state: DatabaseBackend) -> None:
        self._state = state
        self._lock = threading.RLock()
        self._known_secrets: set[str] = set()
        self._subscribers: list[Callable[[WorkflowEvent], None]] = []

    # -- secret registry ----------------------------------------------------

    def register_secret(self, secret: str) -> None:
        """Register a known raw secret value to scrub from every future payload.

        Used as defense-in-depth: callers that briefly hold a raw value (for
        example while constructing a provider session) can register it so it can
        never appear in an emitted event payload (Requirement 21.4).
        """
        if secret:
            with self._lock:
                self._known_secrets.add(secret)

    # -- subscriptions ------------------------------------------------------

    def subscribe(self, callback: Callable[[WorkflowEvent], None]) -> None:
        """Register a callback invoked with each emitted :class:`WorkflowEvent`.

        Enables the WebSocket server to stream events to the Frontend without the
        Event_Router depending on the transport. Subscriber errors are logged and
        never interrupt persistence or other subscribers.
        """
        with self._lock:
            self._subscribers.append(callback)

    # -- emission -----------------------------------------------------------

    def emit(
        self,
        run_id: str,
        event_type: str,
        message: str,
        *,
        step_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> WorkflowEvent:
        """Normalize, redact, attribute, persist, and fan out one event.

        Every event MUST carry a non-empty ``run_id`` (Requirement 21.5); a
        missing run id is a programming error and raises ``ValueError``.
        """
        if not run_id:
            raise ValueError("a workflow event must be attributable to a run_id")

        redacted_payload = redact_secrets(payload or {}, tuple(self._known_secrets))
        created_at = now_iso()

        with self._lock:
            seq = self._next_seq(run_id)
            event = WorkflowEvent(
                run_id=run_id,
                seq=seq,
                type=event_type,
                step_id=step_id,
                message=message,
                payload=redacted_payload,
                created_at=created_at,
            )
            self._persist(event)
            self._notify(event)
        return event

    def normalize_kernel_event(
        self,
        record: Any,
        *,
        run_id: str | None = None,
    ) -> WorkflowEvent | None:
        """Normalize a Kernel event into a workflow event, or return ``None``.

        A Kernel event becomes a workflow event only when it can be attributed to
        a ``Workflow_Run`` (Requirement 21.5). The run id is taken from the
        explicit ``run_id`` argument when provided, otherwise from the event's
        attributes (``run_id`` / ``workflow_run_id``). Kernel events with no run
        association are not orchestration events and are dropped (``None``).

        ``record`` is duck-typed: it may be a :class:`cp.events.KernelEventRecord`
        or any object exposing ``event_type``/``status``/``message``/``attributes``
        (or a mapping with those keys).
        """
        attributes = _get(record, "attributes", {}) or {}
        resolved_run_id = (
            run_id
            or attributes.get("run_id")
            or attributes.get("workflow_run_id")
        )
        if not resolved_run_id:
            return None

        step_id = attributes.get("step_id")
        message = str(_get(record, "message", "") or "")
        payload = {
            "kernel_event_type": str(_get(record, "event_type", "") or ""),
            "resource_type": str(_get(record, "resource_type", "") or ""),
            "resource_id": str(_get(record, "resource_id", "") or ""),
            "status": str(_get(record, "status", "") or ""),
            "attributes": dict(attributes),
        }
        return self.emit(
            str(resolved_run_id),
            WorkflowEventType.KERNEL_EVENT,
            message or payload["kernel_event_type"] or "kernel event",
            step_id=str(step_id) if step_id else None,
            payload=payload,
        )

    # -- history ------------------------------------------------------------

    def history(self, run_id: str) -> list[WorkflowEvent]:
        """Return the persisted event history for a run, ordered by ``seq``.

        Backs the run-observation API (Requirement 4.5) and restart recovery.
        """
        rows = self._state.fetch_all(
            "SELECT run_id, seq, type, step_id, message, payload_json, created_at "
            "FROM workflow_events WHERE run_id = ? ORDER BY seq ASC",
            (run_id,),
        )
        return [
            WorkflowEvent(
                run_id=row["run_id"],
                seq=int(row["seq"]),
                type=row["type"],
                step_id=row["step_id"],
                message=row["message"],
                payload=from_json(row["payload_json"], {}),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    # -- internals ----------------------------------------------------------

    def _next_seq(self, run_id: str) -> int:
        row = self._state.fetch_one(
            "SELECT MAX(seq) AS max_seq FROM workflow_events WHERE run_id = ?",
            (run_id,),
        )
        current = row.get("max_seq") if row else None
        return (int(current) if current is not None else 0) + 1

    def _persist(self, event: WorkflowEvent) -> None:
        self._state.execute(
            "INSERT INTO workflow_events "
            "(run_id, seq, type, step_id, message, payload_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                event.run_id,
                event.seq,
                event.type,
                event.step_id,
                event.message,
                to_json(event.payload),
                event.created_at,
            ),
        )

    def _notify(self, event: WorkflowEvent) -> None:
        for callback in self._subscribers:
            try:
                callback(event)
            except Exception:  # noqa: BLE001 - a bad subscriber must not break others
                LOGGER.exception("workflow event subscriber raised; continuing")


def _get(record: Any, key: str, default: Any) -> Any:
    """Read ``key`` from a mapping or an attribute-bearing object."""
    if isinstance(record, dict):
        return record.get(key, default)
    return getattr(record, key, default)
