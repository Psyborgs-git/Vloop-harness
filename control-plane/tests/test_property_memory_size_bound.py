"""Property-based test for Memory_Store size-bound enforcement.

# Feature: orchestration-engine-completion, Property 29: Memory size bound is enforced

Property 29 states that *for any* sequence of Memory_Entry additions, the total
persisted size never exceeds the configured maximum; when an addition would
exceed it, curation rejects or removes entries to stay within bound.

This test drives random sequences of records against a bounded
:class:`~core.memory_store.MemoryStore` backed by a temporary SQLite database
and asserts the invariant under both curation strategies:

* With :data:`~core.memory_store.OVERFLOW_EVICT_OLDEST`, after any sequence of
  records ``total_size()`` never exceeds ``max_total_bytes``.
* With :data:`~core.memory_store.OVERFLOW_REJECT`, a record that would overflow
  the bound raises :class:`~core.memory_store.MemoryStoreError`, leaves the
  store unchanged, and the store always stays within the bound.

A per-entry record whose own size exceeds the whole bound can never fit and
raises ``MemoryStoreError`` regardless of strategy; the test treats that as an
expected rejection that must leave the store within bound.

**Validates: Requirements 11.2**
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.database import SQLiteBackend
from core.memory_store import (
    OVERFLOW_EVICT_OLDEST,
    OVERFLOW_REJECT,
    MemoryStore,
    MemoryStoreError,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Small bound so that random sequences realistically trigger overflow/curation.
_max_total_bytes = st.integers(min_value=1, max_value=64)

# Record contents kept small (and possibly multi-byte) so a sequence exercises
# the bound from below, at, and above. Empty strings are allowed (0 bytes).
_contents = st.lists(st.text(max_size=32), min_size=0, max_size=30)


def _ids(store: MemoryStore) -> list[str]:
    return [e["id"] for e in store.list_entries()]


# ---------------------------------------------------------------------------
# Property 29: Memory size bound is enforced
# ---------------------------------------------------------------------------


@settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(max_total_bytes=_max_total_bytes, contents=_contents)
def test_evict_oldest_never_exceeds_bound(
    max_total_bytes: int, contents: list[str]
) -> None:
    """Evict-oldest: total_size() never exceeds the bound after any sequence."""
    with tempfile.TemporaryDirectory() as tmp:
        backend = SQLiteBackend(Path(tmp) / "memory.db")
        store = MemoryStore(
            backend,
            max_total_bytes=max_total_bytes,
            on_overflow=OVERFLOW_EVICT_OLDEST,
        )
        for content in contents:
            try:
                store.record(content)
            except MemoryStoreError:
                # Only legitimate rejection: the entry alone exceeds the bound.
                assert len(content.encode("utf-8")) > max_total_bytes
            # Invariant holds after every record, success or rejection.
            assert store.total_size() <= max_total_bytes


@settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(max_total_bytes=_max_total_bytes, contents=_contents)
def test_reject_overflow_leaves_store_within_bound_and_unchanged(
    max_total_bytes: int, contents: list[str]
) -> None:
    """Reject: overflowing records raise and leave the store unchanged."""
    with tempfile.TemporaryDirectory() as tmp:
        backend = SQLiteBackend(Path(tmp) / "memory.db")
        store = MemoryStore(
            backend,
            max_total_bytes=max_total_bytes,
            on_overflow=OVERFLOW_REJECT,
        )
        for content in contents:
            size = len(content.encode("utf-8"))
            before_total = store.total_size()
            before_ids = _ids(store)
            would_overflow = before_total + size > max_total_bytes

            if would_overflow:
                try:
                    store.record(content)
                except MemoryStoreError:
                    pass
                else:  # pragma: no cover - asserts the expected raise happened
                    raise AssertionError(
                        "expected MemoryStoreError for overflowing record under "
                        "the reject strategy"
                    )
                # The store is unchanged after a rejected addition.
                assert store.total_size() == before_total
                assert _ids(store) == before_ids
            else:
                store.record(content)
                assert store.total_size() == before_total + size

            # The bound invariant always holds.
            assert store.total_size() <= max_total_bytes
