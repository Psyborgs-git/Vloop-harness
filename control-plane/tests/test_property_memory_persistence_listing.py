"""Property-based test for Memory_Store persistence and listing.

# Feature: orchestration-engine-completion, Property 28: Memory persistence and listing

Property 28 states that for any set of recorded Memory_Entries, the entries
persist across a store reload and the list API returns exactly the stored set.

Concretely, for any sequence of ``record`` operations applied to a fresh
:class:`~core.memory_store.MemoryStore` backed by a temporary SQLite file:

* every recorded entry is retrievable via :meth:`MemoryStore.list_entries`
  (Requirement 11.4 — the listing API returns all current entries); and
* the same entries remain retrievable after constructing a brand-new
  :class:`MemoryStore` over the *same* SQLite file, proving cross-session
  persistence (Requirement 11.1 — entries are available in later sessions).

The ``memory_entry_sequences()`` strategy uses a generous ``max_total_bytes``
budget so that size-bound curation (Requirement 11.2, covered separately by
Property 29) never evicts entries and interferes with this property.

**Validates: Requirements 11.1, 11.4**
"""

from __future__ import annotations

from pathlib import Path
import tempfile

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.database import SQLiteBackend
from core.memory_store import MemoryStore

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Categories mirror the design's preference|project|environment set, plus an
# arbitrary text category to keep the store forward-compatible.
_categories = st.one_of(
    st.sampled_from(["preference", "project", "environment"]),
    st.text(min_size=1, max_size=12),
)


@st.composite
def memory_entry_sequences(draw: st.DrawFn) -> list[dict[str, str]]:
    """Generate a sequence of ``record`` operations.

    Each operation is a ``{"content", "category"}`` dict. Content is kept small
    so that, combined with a generous ``max_total_bytes`` budget chosen by the
    test, the total never approaches the size bound and curation never evicts
    entries (which would otherwise interfere with Property 28).
    """
    record = st.fixed_dictionaries(
        {
            "content": st.text(min_size=0, max_size=64),
            "category": _categories,
        }
    )
    return draw(st.lists(record, min_size=0, max_size=20))


# A budget large enough that the worst-case sequence (20 entries * 64 chars,
# each char up to 4 UTF-8 bytes) cannot reach it, so curation never runs.
_GENEROUS_MAX_BYTES = 20 * 64 * 4 * 8


# ---------------------------------------------------------------------------
# Property 28: Memory persistence and listing
# ---------------------------------------------------------------------------


# ``deadline=None``: each example performs real SQLite disk I/O (a temp file
# plus two MemoryStore/SQLiteBackend constructions), so per-example timings vary
# and are not a meaningful signal for this persistence property.
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(operations=memory_entry_sequences())
def test_memory_persistence_and_listing(operations: list[dict[str, str]]) -> None:
    """Recorded entries are listed and survive a new store over the same file."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "memory-prop.db"

        # Session 1: record every operation against a fresh store.
        writer = MemoryStore(SQLiteBackend(db_path), max_total_bytes=_GENEROUS_MAX_BYTES)
        recorded: list[dict] = [
            writer.record(op["content"], category=op["category"]) for op in operations
        ]
        recorded_by_id = {entry["id"]: entry for entry in recorded}

        # Req 11.4: list_entries returns exactly the set of current entries.
        listed = writer.list_entries()
        assert {e["id"] for e in listed} == set(recorded_by_id)
        assert len(listed) == len(recorded)
        for entry in listed:
            expected = recorded_by_id[entry["id"]]
            assert entry["content"] == expected["content"]
            assert entry["category"] == expected["category"]

        # Req 11.1: a brand-new store over the same SQLite file sees every entry,
        # demonstrating cross-session persistence (no reliance on in-memory state).
        reader = MemoryStore(SQLiteBackend(db_path), max_total_bytes=_GENEROUS_MAX_BYTES)
        reloaded = reader.list_entries()
        assert {e["id"] for e in reloaded} == set(recorded_by_id)
        assert len(reloaded) == len(recorded)
        for entry in reloaded:
            expected = recorded_by_id[entry["id"]]
            assert entry["content"] == expected["content"]
            assert entry["category"] == expected["category"]
            # Each entry is also retrievable individually after the reload.
            fetched = reader.get(entry["id"])
            assert fetched is not None
            assert fetched["content"] == expected["content"]
