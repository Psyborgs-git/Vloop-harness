"""Property-based test for Event_Router secret redaction.

# Feature: orchestration-engine-completion, Property 45: Secrets are redacted from all outputs

Property 45 states that *for any* log entry, event, or Frontend-facing response,
secret values are redacted and never appear in the emitted output.

This test focuses on the Event_Router emission path (``core/event_router.py``),
which is the single choke point every workflow event flows through before it
reaches a log, the ``workflow_events`` table, or the Frontend. It generates
payloads that nest registered raw secret values and sensitive-looking keys
arbitrarily inside dicts and lists, emits them through :class:`EventRouter`, and
asserts:

* no raw registered secret value appears anywhere in the emitted event payload;
* no raw registered secret value appears in the persisted ``payload_json``;
* values under sensitive keys (``api_key``, ``password``, ...) are replaced with
  the :data:`REDACTED` placeholder; and
* grant-reference keys (``grant_id``, ``session_ref``, ...) survive unredacted,
  since they are references rather than secrets.

**Validates: Requirements 21.4**
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.database import SQLiteBackend
from core.event_router import (
    REDACTED,
    EventRouter,
    WorkflowEventType,
)

# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

# A small pool of distinctive raw secret values. They are deliberately unusual
# strings so that, after redaction, finding any of them verbatim in an output is
# unambiguous evidence of a leak (not an accidental substring of normal text).
_SECRET_VALUES: tuple[str, ...] = (
    "sk-live-DEADBEEF0123456789",
    "ghp_ZZZ9988776655443322110",
    "AKIA__SECRET__ACCESS__KEY__",
    "xoxb-super-secret-slack-token",
    "pk_test_RAWSECRETVALUE98765",
)

# Keys recognized as sensitive by the Event_Router's key-based redaction.
_SENSITIVE_KEYS: tuple[str, ...] = (
    "api_key",
    "apikey",
    "password",
    "passwd",
    "secret",
    "secret_key",
    "access_key",
    "private_key",
    "client_secret",
    "token",
    "authorization",
    "bearer",
    "credential",
)

# Grant-reference keys that must NOT be redacted (they carry references, not
# raw secret material) and the sentinel values used to confirm they survive.
_GRANT_KEYS: tuple[str, ...] = (
    "grant_id",
    "session_ref",
    "grant_ref",
    "kernel_snapshot_ref",
)
_GRANT_SENTINEL = "grant-reference-survives-OK"


secret_values = st.sampled_from(_SECRET_VALUES)


def _benign_scalars() -> st.SearchStrategy[Any]:
    return st.one_of(
        st.none(),
        st.booleans(),
        st.integers(min_value=-(10**6), max_value=10**6),
        st.text(alphabet="abcdefghijklmnopqrstuvwxyz ", max_size=12),
    )


@st.composite
def secret_bearing_strings(draw: st.DrawFn) -> str:
    """A string that embeds a raw secret value, possibly inside benign text."""
    secret = draw(secret_values)
    prefix = draw(st.text(alphabet="abcdef ", max_size=8))
    suffix = draw(st.text(alphabet="ghijkl ", max_size=8))
    return f"{prefix}{secret}{suffix}"


def payloads() -> st.SearchStrategy[dict]:
    """Generate payload dicts nesting secrets and sensitive keys arbitrarily.

    The recursive structure mixes:
    * benign scalars and text;
    * strings that embed a raw secret value (to exercise value-based scrubbing);
    * dict entries under sensitive keys (to exercise key-based redaction).
    """
    leaves = st.one_of(
        _benign_scalars(),
        secret_values,
        secret_bearing_strings(),
    )

    def _extend(children: st.SearchStrategy[Any]) -> st.SearchStrategy[Any]:
        benign_keys = st.text(alphabet="abcdefghijklmnop_", max_size=8)
        keys = st.one_of(benign_keys, st.sampled_from(_SENSITIVE_KEYS))
        return st.one_of(
            st.lists(children, max_size=4),
            st.dictionaries(keys, children, max_size=4),
        )

    nested = st.recursive(leaves, _extend, max_leaves=15)
    # Top level is always a dict, matching how payloads are emitted.
    return st.dictionaries(
        st.one_of(st.text(alphabet="abcdefghijklmnop_", max_size=8),
                  st.sampled_from(_SENSITIVE_KEYS)),
        nested,
        max_size=6,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _iter_strings(value: Any):
    """Yield every string found anywhere within a nested dict/list structure."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            if isinstance(k, str):
                yield k
            yield from _iter_strings(v)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_strings(item)


def _find_sensitive_key_values(value: Any):
    """Yield values that sit directly under a sensitive (non-grant) key."""
    if isinstance(value, dict):
        for k, v in value.items():
            if isinstance(k, str):
                lowered = k.lower()
                is_grant = lowered in {gk.lower() for gk in _GRANT_KEYS}
                if not is_grant and any(s in lowered for s in _SENSITIVE_KEYS):
                    yield v
            yield from _find_sensitive_key_values(v)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _find_sensitive_key_values(item)


# ---------------------------------------------------------------------------
# Property 45: Secrets are redacted from all outputs
# ---------------------------------------------------------------------------


# deadline=None: each example performs real SQLite file I/O (open, schema
# init, insert, query), so per-example latency varies with disk/GC timing.
# The property is about redaction correctness, not latency.
@settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(payload=payloads())
def test_secrets_are_redacted_from_all_outputs(payload: dict, tmp_path_factory) -> None:
    """No registered raw secret survives emission; grant references do survive."""
    db_path = tmp_path_factory.mktemp("redaction") / "events.db"
    backend = SQLiteBackend(db_path)
    router = EventRouter(backend)

    # Register every known secret value so value-based scrubbing applies, even
    # when a secret lands under an innocuous (non-sensitive) key.
    for secret in _SECRET_VALUES:
        router.register_secret(secret)

    # Add grant-reference keys that must survive redaction unchanged.
    enriched: dict[str, Any] = dict(payload)
    for grant_key in _GRANT_KEYS:
        enriched[grant_key] = _GRANT_SENTINEL

    event = router.emit(
        "run-redaction",
        WorkflowEventType.KERNEL_EVENT,
        "provisioning in progress",
        payload=enriched,
    )

    # 1. No raw secret value appears anywhere in the emitted payload.
    for text in _iter_strings(event.payload):
        for secret in _SECRET_VALUES:
            assert secret not in text, f"raw secret leaked into emitted payload: {text!r}"

    # 2. No raw secret survives in the persisted payload_json.
    row = backend.fetch_one(
        "SELECT payload_json FROM workflow_events WHERE run_id = ? AND seq = ?",
        ("run-redaction", event.seq),
    )
    assert row is not None
    stored_json = row["payload_json"]
    for secret in _SECRET_VALUES:
        assert secret not in stored_json, "raw secret leaked into persisted payload_json"

    # The persisted payload must round-trip back into the same redacted shape.
    assert json.loads(stored_json) == event.payload

    # 3. Every value under a sensitive key was replaced wholesale with REDACTED.
    for redacted_value in _find_sensitive_key_values(event.payload):
        assert redacted_value == REDACTED

    # 4. Grant-reference keys survive unredacted (references, not secrets).
    for grant_key in _GRANT_KEYS:
        assert event.payload[grant_key] == _GRANT_SENTINEL
