"""Unit tests for the Memory_Store (`core/memory_store.py`).

Covers task 22.1: persistence across sessions (Req 11.1), size-bound curation
with reject/evict on overflow (Req 11.2), deletion independent of a completion
flag with a descriptive error on failure (Req 11.3), and the listing API
(Req 11.4).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.database import SQLiteBackend
from core.memory_store import (
    OVERFLOW_EVICT_OLDEST,
    OVERFLOW_REJECT,
    MemoryStoreError,
    MemoryStore,
)


@pytest.fixture()
def backend(tmp_path: Path) -> SQLiteBackend:
    return SQLiteBackend(tmp_path / "memory-test.db")


# ---------------------------------------------------------------------------
# Persistence and listing (Req 11.1, 11.4)
# ---------------------------------------------------------------------------


def test_record_persists_and_lists(backend: SQLiteBackend):
    store = MemoryStore(backend, max_total_bytes=1024)
    entry = store.record("User prefers concise answers.", category="preference")

    assert entry["id"]
    assert entry["category"] == "preference"
    assert entry["size_bytes"] == len("User prefers concise answers.".encode())

    listed = store.list_entries()
    assert len(listed) == 1
    assert listed[0]["id"] == entry["id"]
    assert listed[0]["content"] == "User prefers concise answers."


def test_entries_survive_a_new_store_instance(tmp_path: Path):
    """Req 11.1: a recorded entry is available in a later session/restart."""
    db_path = tmp_path / "persist.db"
    writer = MemoryStore(SQLiteBackend(db_path), max_total_bytes=1024)
    entry = writer.record("project uses Python 3.12", category="environment")

    reader = MemoryStore(SQLiteBackend(db_path), max_total_bytes=1024)
    reloaded = reader.get(entry["id"])
    assert reloaded is not None
    assert reloaded["content"] == "project uses Python 3.12"
    assert reader.list_entries()[0]["id"] == entry["id"]


def test_list_entries_filters_by_category(backend: SQLiteBackend):
    store = MemoryStore(backend, max_total_bytes=1024)
    store.record("a", category="preference")
    store.record("b", category="project")
    store.record("c", category="project")

    assert len(store.list_entries()) == 3
    assert {e["content"] for e in store.list_entries(category="project")} == {"b", "c"}
    assert len(store.list_entries(category="preference")) == 1


def test_get_returns_none_for_missing(backend: SQLiteBackend):
    store = MemoryStore(backend, max_total_bytes=1024)
    assert store.get("does-not-exist") is None


# ---------------------------------------------------------------------------
# Size-bound curation (Req 11.2)
# ---------------------------------------------------------------------------


def test_total_size_tracks_entries(backend: SQLiteBackend):
    store = MemoryStore(backend, max_total_bytes=1024)
    assert store.total_size() == 0
    store.record("12345")  # 5 bytes
    assert store.total_size() == 5
    store.record("678")  # 3 bytes
    assert store.total_size() == 8


def test_evict_makes_room_on_overflow(backend: SQLiteBackend):
    store = MemoryStore(backend, max_total_bytes=10, on_overflow=OVERFLOW_EVICT_OLDEST)
    store.record("aaaaa")  # 5 bytes
    store.record("bbbbb")  # 5 bytes -> total 10, at the bound
    assert store.total_size() == 10

    # Adding 5 more bytes would exceed 10; curation evicts to make room.
    third = store.record("ccccc")
    ids = {e["id"] for e in store.list_entries()}
    assert third["id"] in ids  # the new entry is stored
    assert store.total_size() <= 10  # stays within the configured bound


def test_evict_oldest_evicts_in_creation_order(backend: SQLiteBackend):
    """Eviction is best-effort oldest-first, ordered by (created_at, id).

    Timestamps are forced distinct so creation order is unambiguous.
    """
    from unittest import mock

    store = MemoryStore(backend, max_total_bytes=10, on_overflow=OVERFLOW_EVICT_OLDEST)
    with mock.patch("core.memory_store.now_iso", side_effect=[
        "2024-01-01T00:00:01Z",
        "2024-01-01T00:00:02Z",
        "2024-01-01T00:00:03Z",
    ]):
        first = store.record("aaaaa")
        second = store.record("bbbbb")
        third = store.record("ccccc")

    ids = {e["id"] for e in store.list_entries()}
    assert first["id"] not in ids  # oldest evicted
    assert second["id"] in ids
    assert third["id"] in ids
    assert store.total_size() == 10


def test_reject_strategy_refuses_overflow_with_descriptive_error(backend: SQLiteBackend):
    store = MemoryStore(backend, max_total_bytes=10, on_overflow=OVERFLOW_REJECT)
    store.record("aaaaa")
    store.record("bbbbb")  # total 10
    with pytest.raises(MemoryStoreError) as exc:
        store.record("ccccc")
    assert "maximum total size" in str(exc.value)
    # The store is unchanged after a rejected addition.
    assert store.total_size() == 10
    assert len(store.list_entries()) == 2


def test_entry_larger_than_bound_is_rejected(backend: SQLiteBackend):
    store = MemoryStore(backend, max_total_bytes=4, on_overflow=OVERFLOW_EVICT_OLDEST)
    with pytest.raises(MemoryStoreError) as exc:
        store.record("toolong")  # 7 bytes > 4
    assert "exceeds the configured maximum" in str(exc.value)
    assert store.list_entries() == []


# ---------------------------------------------------------------------------
# Deletion (Req 11.3)
# ---------------------------------------------------------------------------


def test_delete_removes_from_persistence(backend: SQLiteBackend):
    store = MemoryStore(backend, max_total_bytes=1024)
    entry = store.record("delete me")
    store.delete(entry["id"])
    assert store.get(entry["id"]) is None
    assert store.list_entries() == []


def test_delete_missing_entry_raises_descriptive_error(backend: SQLiteBackend):
    store = MemoryStore(backend, max_total_bytes=1024)
    with pytest.raises(MemoryStoreError) as exc:
        store.delete("nope")
    assert "no such entry" in str(exc.value)


def test_delete_is_independent_of_other_entries(backend: SQLiteBackend):
    store = MemoryStore(backend, max_total_bytes=1024)
    keep = store.record("keep")
    drop = store.record("drop")
    store.delete(drop["id"])
    remaining = [e["id"] for e in store.list_entries()]
    assert remaining == [keep["id"]]


# ---------------------------------------------------------------------------
# Configuration guards
# ---------------------------------------------------------------------------


def test_invalid_overflow_strategy_rejected(backend: SQLiteBackend):
    with pytest.raises(ValueError):
        MemoryStore(backend, max_total_bytes=10, on_overflow="bogus")


def test_negative_max_rejected(backend: SQLiteBackend):
    with pytest.raises(ValueError):
        MemoryStore(backend, max_total_bytes=-1)
