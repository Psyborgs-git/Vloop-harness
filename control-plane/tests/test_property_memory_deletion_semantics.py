"""Property-based test for Memory_Store deletion semantics.

# Feature: orchestration-engine-completion, Property 30: Memory deletion removes from persistence

Property 30 states that for any Memory_Entry deletion request, the entry is
removed from persistence independently of any completion flag; if deletion
cannot complete (e.g. the id does not exist) a descriptive error is returned.

This test records a random set of entries, deletes an arbitrary subset, and
asserts that:

* every deleted entry is gone from persistence — ``get`` returns ``None`` and it
  is absent from ``list_entries`` — including when observed through a *new*
  ``MemoryStore`` instance opened on the same SQLite file (proving the removal
  is durable, not just in-memory);
* every non-deleted entry remains present with its original content;
* deleting an id that is not present raises :class:`MemoryStoreError`.

**Validates: Requirements 11.3**
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.database import SQLiteBackend
from core.memory_store import MemoryStore, MemoryStoreError

# A budget far larger than any generated payload so curation/eviction never
# interferes with what we are testing here (deletion, not size-bound curation).
_MAX_TOTAL_BYTES = 1 << 24

_CATEGORIES = ["preference", "project", "environment"]


@st.composite
def _entries(draw: st.DrawFn) -> list[dict[str, str]]:
    """Generate a non-empty list of (category, content) entries to record."""
    count = draw(st.integers(min_value=1, max_value=8))
    contents = draw(
        st.lists(
            st.text(min_size=1, max_size=40),
            min_size=count,
            max_size=count,
        )
    )
    categories = draw(
        st.lists(
            st.sampled_from(_CATEGORIES),
            min_size=count,
            max_size=count,
        )
    )
    return [
        {"category": cat, "content": content}
        for cat, content in zip(categories, contents)
    ]


@settings(
    max_examples=100,
    deadline=None,  # per-example SQLite file setup makes per-run timing variable
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    specs=_entries(),
    delete_mask=st.data(),
)
def test_deletion_removes_from_persistence(specs, delete_mask) -> None:
    """Deleted entries vanish durably; survivors remain; missing id errors."""
    # Choose an arbitrary subset of indices to delete.
    to_delete_flags = delete_mask.draw(
        st.lists(st.booleans(), min_size=len(specs), max_size=len(specs))
    )

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "memory-deletion.db"
        store = MemoryStore(SQLiteBackend(db_path), max_total_bytes=_MAX_TOTAL_BYTES)

        # Record every generated entry; remember its assigned id and content.
        recorded: list[dict[str, str]] = []
        for spec in specs:
            entry = store.record(spec["content"], category=spec["category"])
            recorded.append({"id": entry["id"], "content": spec["content"]})

        deleted_ids = {
            recorded[i]["id"]
            for i, flag in enumerate(to_delete_flags)
            if flag
        }
        surviving = {
            r["id"]: r["content"]
            for i, r in enumerate(recorded)
            if not to_delete_flags[i]
        }

        # Delete the chosen subset.
        for entry_id in deleted_ids:
            store.delete(entry_id)

        # Deleting an id that is not present raises a descriptive error.
        missing_id = uuid.uuid4().hex
        with pytest.raises(MemoryStoreError):
            store.delete(missing_id)
        # Re-deleting an already-deleted id is also a missing-entry error.
        for entry_id in deleted_ids:
            with pytest.raises(MemoryStoreError):
                store.delete(entry_id)

        # Verify on the original instance.
        _assert_state(store, deleted_ids, surviving)

        # Verify durability: a brand-new MemoryStore over the same file sees the
        # same post-deletion state (persistence, not just in-memory bookkeeping).
        reopened = MemoryStore(
            SQLiteBackend(db_path), max_total_bytes=_MAX_TOTAL_BYTES
        )
        _assert_state(reopened, deleted_ids, surviving)


def _assert_state(
    store: MemoryStore,
    deleted_ids: set[str],
    surviving: dict[str, str],
) -> None:
    """Assert deleted ids are gone and surviving ids are present & intact."""
    listed = {e["id"]: e["content"] for e in store.list_entries()}

    for entry_id in deleted_ids:
        assert store.get(entry_id) is None, f"deleted id {entry_id} still readable"
        assert entry_id not in listed, f"deleted id {entry_id} still listed"

    for entry_id, content in surviving.items():
        got = store.get(entry_id)
        assert got is not None, f"surviving id {entry_id} disappeared"
        assert got["content"] == content
        assert listed.get(entry_id) == content

    # Listing reflects exactly the surviving set.
    assert set(listed) == set(surviving)
