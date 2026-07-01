"""Property-based test for Credential_Pool rotation and rejection handling.

# Feature: orchestration-engine-completion, Property 42: Credential pool rotation and rejection handling

Property 42 states that *for any* configured Credential_Pool and sequence of
successive calls, the :class:`CredentialPoolManager`:

* **Rotates across the pool's grants (Req 19.2).** Successive ``acquire`` calls
  advance round-robin across the pool's non-quarantined secret references.
* **Quarantines rejected grants (Req 19.3).** A grant the provider rejects is
  removed from rotation, never returned again, and recorded in
  :attr:`CredentialPoolManager.quarantined` for review. When every grant in the
  pool is quarantined, ``acquire`` returns ``None``.

The test generates a random pool of unique secret references and a random
sequence of ``acquire``/``quarantine`` operations, then drives the manager while
mirroring its round-robin cursor in an independent reference model. Each
``acquire`` result is checked against the model, and the quarantine log plus the
all-quarantined exhaustion behaviour are asserted.

An injectable grant source maps each secret reference to an opaque
:class:`GrantContext` (a grant id + session ref, never a raw secret value).

**Validates: Requirements 19.2, 19.3**
"""

from __future__ import annotations

import string
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from core.inference_gateway import CredentialPoolManager
from core.orchestration_types import GrantContext

PROVIDER = "p"


def _grant_source(secret_ref: str, target: str) -> GrantContext:
    """Map a secret ref to an opaque session context (never a raw secret)."""
    return GrantContext(
        grant_id=f"grant::{secret_ref}", session_ref=f"sess::{secret_ref}"
    )


# ---------------------------------------------------------------------------
# Reference model of the round-robin cursor (independent of the implementation)
# ---------------------------------------------------------------------------


class _Model:
    """Mirrors the manager's round-robin selection over non-quarantined refs."""

    def __init__(self, refs: list[str]) -> None:
        self._refs = refs
        self._cursor = 0
        self.quarantined: set[str] = set()

    def acquire(self) -> str | None:
        n = len(self._refs)
        start = self._cursor
        for offset in range(n):
            idx = (start + offset) % n
            ref = self._refs[idx]
            if ref not in self.quarantined:
                self._cursor = (idx + 1) % n
                return ref
        return None

    def quarantine(self, ref: str) -> None:
        self.quarantined.add(ref)


# ---------------------------------------------------------------------------
# Strategies: a random pool + a random acquire/quarantine op sequence
# ---------------------------------------------------------------------------

_SECRET_REF = st.text(
    alphabet=string.ascii_letters + string.digits + "_-", min_size=1, max_size=8
)


@st.composite
def scenarios(draw: st.DrawFn) -> dict[str, Any]:
    refs = draw(st.lists(_SECRET_REF, min_size=1, max_size=6, unique=True))
    # Each op is "acquire" or "quarantine"; quarantine acts on a recently
    # acquired grant, so acquires must dominate for the sequence to be useful.
    ops = draw(
        st.lists(
            st.sampled_from(["acquire", "acquire", "acquire", "quarantine"]),
            min_size=1,
            max_size=30,
        )
    )
    return {"refs": refs, "ops": ops}


# ---------------------------------------------------------------------------
# Property 42
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(case=scenarios())
def test_credential_pool_rotation_and_rejection(case: dict[str, Any]) -> None:
    refs: list[str] = case["refs"]
    ops: list[str] = case["ops"]

    manager = CredentialPoolManager(_grant_source, pools={PROVIDER: refs})
    model = _Model(refs)

    # Grants acquired but not yet quarantined, eligible for a quarantine op.
    live_refs: list[str] = []
    quarantined_refs: set[str] = set()

    for op in ops:
        if op == "acquire":
            expected_ref = model.acquire()
            grant = manager.acquire(PROVIDER, target="inference:p")
            if expected_ref is None:
                # Req 19.3: when every grant is quarantined, acquire returns None.
                assert grant is None
            else:
                assert grant is not None
                # Req 19.2: rotation matches the round-robin model exactly.
                assert grant.grant_id == f"grant::{expected_ref}"
                # Req 19.3: a quarantined grant is never returned again.
                assert expected_ref not in quarantined_refs
                if expected_ref not in live_refs:
                    live_refs.append(expected_ref)
        else:  # quarantine
            if not live_refs:
                continue
            victim_ref = live_refs.pop()
            grant = GrantContext(
                grant_id=f"grant::{victim_ref}", session_ref=f"sess::{victim_ref}"
            )
            manager.quarantine(PROVIDER, grant, reason="provider rejected grant")
            model.quarantine(victim_ref)
            quarantined_refs.add(victim_ref)

            # Req 19.3: the rejected grant is recorded for review.
            recorded = {q.secret_ref for q in manager.quarantined}
            assert victim_ref in recorded

    # Req 19.3: every quarantined ref is recorded, and none are extraneous.
    recorded = {q.secret_ref for q in manager.quarantined}
    assert recorded == quarantined_refs
    for entry in manager.quarantined:
        assert entry.provider_id == PROVIDER
        assert entry.grant_id == f"grant::{entry.secret_ref}"

    # Req 19.3: draining the pool by quarantining every remaining grant
    # eventually exhausts it, after which acquire returns None.
    for _ in range(len(refs)):
        grant = manager.acquire(PROVIDER, target="inference:p")
        if grant is None:
            break
        manager.quarantine(PROVIDER, grant, reason="drain")

    assert manager.acquire(PROVIDER, target="inference:p") is None
