"""Property-based test: no raw secret values in Control_Plane state.

# Feature: orchestration-engine-completion, Property 19: No raw secret values in Control_Plane state

Property 19 states that *for any* sequence of model calls or MCP connections,
Control_Plane application state (including any in-memory credential cache)
contains only granted session context and grant references, never raw secret
values (Requirements 6.5, 18.4).

This test exercises the credential path that the Inference_Gateway and MCP_Client
use: credentials are obtained only via Kernel grants, and the
:class:`CredentialPoolManager` caches only :class:`GrantContext` (a grant id +
opaque session reference). The grant source mimics the Kernel by issuing a
``GrantContext`` that references a distinctive raw secret *out of band* — the raw
secret value is NEVER placed into the ``GrantContext`` or returned to the
Control_Plane.

For random secret references, targets, and raw secret values the test acquires
and rotates grants through the pool manager, then asserts:

* the raw secret value never appears in any issued ``GrantContext``;
* the raw secret value never appears in the pool manager's cached or quarantine
  state, nor in anything it exposes — verified by serializing the manager's
  entire reachable state to a string and asserting the raw-secret substring is
  absent;
* ``GrantContext.__slots__`` is exactly ``{"grant_id", "session_ref"}`` so the
  type structurally cannot hold a raw secret value.

**Validates: Requirements 6.5, 18.4**
"""

from __future__ import annotations

import string
from typing import Dict, Tuple

from hypothesis import given, settings
from hypothesis import strategies as st

from core.inference_gateway import CredentialPoolManager
from core.orchestration_types import GrantContext


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# A distinctive, high-entropy raw secret value. The marker prefix makes the
# substring search unambiguous and very unlikely to collide with grant ids,
# session refs, provider ids, or secret references generated below.
_RAW_SECRET = st.text(
    alphabet=string.ascii_letters + string.digits, min_size=8, max_size=24
).map(lambda s: f"RAWSECRET-{s}-VALUE")

_IDENT = st.text(
    alphabet=string.ascii_lowercase + string.digits, min_size=1, max_size=8
)

# A provider with a small pool of distinct secret references so rotation across
# successive acquisitions is exercised.
_SECRET_REFS = st.lists(_IDENT, min_size=1, max_size=4, unique=True)


# ---------------------------------------------------------------------------
# Out-of-band grant source: the raw secret stays with the "Kernel"
# ---------------------------------------------------------------------------


class _OutOfBandGrantSource:
    """Issues GrantContexts that reference a raw secret held out of band.

    Mimics the Kernel secret manager: the raw secret value lives only in this
    source's private vault (keyed by grant id) and is *never* placed into the
    returned :class:`GrantContext`. The Control_Plane only ever sees the grant
    id and an opaque session reference.
    """

    def __init__(self, raw_secret: str) -> None:
        self._raw_secret = raw_secret
        self._vault: Dict[str, str] = {}
        self._counter = 0

    def __call__(self, secret_ref: str, target: str) -> GrantContext:
        self._counter += 1
        grant_id = f"grant-{self._counter}"
        session_ref = f"session-{secret_ref}-{self._counter}"
        # The raw secret is retained out of band, never in the GrantContext.
        self._vault[grant_id] = self._raw_secret
        return GrantContext(grant_id=grant_id, session_ref=session_ref)


# ---------------------------------------------------------------------------
# Deep state serialization helper
# ---------------------------------------------------------------------------


def _serialize_state(obj: object, _seen: set[int] | None = None) -> str:
    """Render an object's reachable state to a single string.

    Walks ``__dict__``/``__slots__``, mappings, and iterables so that any raw
    secret stored anywhere in the manager's reachable state would surface in the
    resulting string. Recursion is guarded against cycles.
    """
    if _seen is None:
        _seen = set()
    oid = id(obj)
    if oid in _seen:
        return "<cycle>"
    if obj is None or isinstance(obj, (bool, int, float)):
        return repr(obj)
    if isinstance(obj, (str, bytes)):
        return obj.decode() if isinstance(obj, bytes) else obj
    _seen.add(oid)

    parts: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            parts.append(_serialize_state(key, _seen))
            parts.append(_serialize_state(value, _seen))
        return " ".join(parts)
    if isinstance(obj, (list, tuple, set, frozenset)):
        for item in obj:
            parts.append(_serialize_state(item, _seen))
        return " ".join(parts)

    # Generic object: collect __dict__ and __slots__ attributes.
    state: Dict[str, object] = {}
    if hasattr(obj, "__dict__"):
        state.update(vars(obj))
    for slot in getattr(type(obj), "__slots__", ()):  # dataclass(slots=True)
        if hasattr(obj, slot):
            state[slot] = getattr(obj, slot)
    if state:
        return _serialize_state(state, _seen)
    return repr(obj)


# ---------------------------------------------------------------------------
# Property 19
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(
    raw_secret=_RAW_SECRET,
    provider_id=_IDENT,
    secret_refs=_SECRET_REFS,
    target=_IDENT,
    rounds=st.integers(min_value=1, max_value=12),
    quarantine_flags=st.lists(st.booleans(), min_size=0, max_size=12),
)
def test_no_raw_secret_values_in_control_plane_state(
    raw_secret: str,
    provider_id: str,
    secret_refs: list[str],
    target: str,
    rounds: int,
    quarantine_flags: list[bool],
) -> None:
    """No raw secret value ever appears in GrantContext or pool-manager state."""
    # GrantContext structurally cannot hold a raw secret value.
    assert set(GrantContext.__slots__) == {"grant_id", "session_ref"}

    source = _OutOfBandGrantSource(raw_secret)
    manager = CredentialPoolManager(source, pools={provider_id: secret_refs})

    issued: list[GrantContext] = []
    for i in range(rounds):
        grant = manager.acquire(provider_id, target=target)
        if grant is None:
            # Pool exhausted (all quarantined) — nothing more to acquire.
            break
        issued.append(grant)
        # No raw secret value ever appears in an issued GrantContext.
        assert raw_secret not in grant.grant_id
        assert raw_secret not in grant.session_ref
        assert raw_secret not in _serialize_state(grant)

        # Occasionally quarantine a rejected grant (Req 19.3) to populate the
        # quarantine state and ensure it too never holds the raw secret.
        if i < len(quarantine_flags) and quarantine_flags[i]:
            manager.quarantine(provider_id, grant, reason="rejected-by-provider")

    # The raw secret must never appear anywhere in the pool manager's reachable
    # state: caches, cursors, quarantine log, or anything else it exposes. The
    # injected grant source represents the Kernel trust boundary (in production a
    # bound method of the kernel adapter); the Kernel legitimately holds raw
    # secrets out of band, so it is excluded from the Control_Plane state walk.
    serialized = _serialize_state(manager, {id(source)})
    assert raw_secret not in serialized, (
        "raw secret value leaked into CredentialPoolManager state"
    )

    # Also assert against the publicly exposed quarantine records.
    quarantined_serialized = _serialize_state(manager.quarantined)
    assert raw_secret not in quarantined_serialized

    # Sanity: the out-of-band vault DID hold the raw secret (proving the test
    # actually routed a distinctive secret that could have leaked).
    if issued:
        assert raw_secret in _serialize_state(source._vault)
