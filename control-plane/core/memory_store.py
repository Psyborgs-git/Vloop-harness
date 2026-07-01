"""Memory_Store — bounded, curated, cross-session memory entries.

The Memory_Store is the Control_Plane subsystem that persists a bounded,
curated set of long-lived facts (preferences, project notes, environment
facts) so they survive across sessions. It owns four responsibilities, each
mapped to an acceptance criterion:

* **Persistence (Requirement 11.1)** — every recorded :class:`Memory_Entry`
  is written through the existing :class:`~core.database.DatabaseBackend` to
  the ``memory_entries`` table, so it is available in later sessions and after
  a Control_Plane restart.
* **Size-bound curation (Requirement 11.2)** — the store enforces a configured
  maximum *total* size (sum of entry sizes in bytes). If recording an entry
  would exceed the bound, curation runs first; curation is permitted either to
  remove existing entries (the default, evicting oldest-first) or to reject the
  new entry when it cannot be made to fit.
* **Deletion (Requirement 11.3)** — deletion removes the entry from
  persistence directly. Removal is *not* coupled to a separate completion flag:
  the row is deleted unconditionally and the result is then verified. If the
  deletion cannot be completed, a descriptive :class:`MemoryStoreError` is raised.
* **Listing (Requirement 11.4)** — :meth:`MemoryStore.list_entries` exposes all
  current entries (optionally filtered by category) for user review.

Persistence uses the schema declared in ``core/database.py``::

    memory_entries(id, category, content, size_bytes, created_at, updated_at)

Identifiers are UUID4 strings and timestamps come from ``core.helpers.now_iso``,
matching the conventions used by the other Control_Plane services.
"""

from __future__ import annotations

import logging
import os
import threading
import uuid
from typing import Any

from core.database import DatabaseBackend
from core.helpers import now_iso

LOGGER = logging.getLogger("vloop.control_plane.memory_store")

# Default maximum total size (in bytes) across all stored entries. Chosen as a
# conservative, non-zero bound; callers normally pass an explicit limit or set
# ``VLOOP_MEMORY_MAX_BYTES``.
DEFAULT_MAX_TOTAL_BYTES = 64 * 1024

# Overflow strategies for curation (Requirement 11.2).
OVERFLOW_EVICT_OLDEST = "evict_oldest"
OVERFLOW_REJECT = "reject"

# Recognized memory categories. Mirrors the design's ``preference|project|
# environment`` set but is not enforced as a hard constraint — unknown
# categories are stored as-is so the store stays forward-compatible.
DEFAULT_CATEGORY = "preference"


class MemoryStoreError(Exception):
    """Raised when a Memory_Store operation cannot be completed.

    Carries a human-readable message describing why the operation failed (for
    example, an entry that cannot fit within the configured bound, or a
    deletion that could not be completed). Requirements 11.2 and 11.3 both
    require a descriptive error rather than a silent failure.
    """


def _content_size(content: str) -> int:
    """Return the UTF-8 byte size used to charge an entry against the bound."""
    return len(content.encode("utf-8"))


class MemoryStore:
    """Persists bounded, curated, cross-session :class:`Memory_Entry` records.

    Thread-safe: a single re-entrant lock serializes size accounting and
    curation so concurrent ``record`` calls cannot race past the bound.

    :param state: the shared :class:`DatabaseBackend`.
    :param max_total_bytes: the configured maximum total size across all
        entries. Defaults to ``VLOOP_MEMORY_MAX_BYTES`` if set, else
        :data:`DEFAULT_MAX_TOTAL_BYTES`.
    :param on_overflow: curation strategy when an addition would exceed the
        bound — :data:`OVERFLOW_EVICT_OLDEST` (default) removes oldest entries
        until the new one fits, :data:`OVERFLOW_REJECT` refuses the addition.
    """

    def __init__(
        self,
        state: DatabaseBackend,
        max_total_bytes: int | None = None,
        on_overflow: str = OVERFLOW_EVICT_OLDEST,
    ) -> None:
        self._state = state
        self._lock = threading.RLock()
        if max_total_bytes is None:
            max_total_bytes = _resolve_max_bytes()
        if max_total_bytes < 0:
            raise ValueError("max_total_bytes must be non-negative")
        if on_overflow not in (OVERFLOW_EVICT_OLDEST, OVERFLOW_REJECT):
            raise ValueError(f"unknown overflow strategy: {on_overflow}")
        self._max_total_bytes = max_total_bytes
        self._on_overflow = on_overflow

    # -- configuration ------------------------------------------------------

    @property
    def max_total_bytes(self) -> int:
        """The configured maximum total size across all entries."""
        return self._max_total_bytes

    def total_size(self) -> int:
        """Return the current total size (bytes) of all stored entries."""
        row = self._state.fetch_one(
            "SELECT COALESCE(SUM(size_bytes), 0) AS total FROM memory_entries"
        )
        return int(row["total"]) if row and row["total"] is not None else 0

    # -- recording (Requirements 11.1, 11.2) --------------------------------

    def record(
        self,
        content: str,
        category: str = DEFAULT_CATEGORY,
        entry_id: str | None = None,
    ) -> dict[str, Any]:
        """Persist a Memory_Entry, curating first if it would exceed the bound.

        Returns the stored entry as a dict. Raises :class:`MemoryStoreError` when the
        entry cannot be stored within the configured bound (Requirement 11.2):
        either because the configured strategy is :data:`OVERFLOW_REJECT`, or
        because the entry alone is larger than the maximum total size and no
        amount of eviction could make room for it.
        """
        if not isinstance(content, str):
            raise TypeError("memory content must be a string")

        size = _content_size(content)
        with self._lock:
            # An entry larger than the whole budget can never fit, regardless of
            # strategy — reject it with a descriptive error (Requirement 11.2).
            if size > self._max_total_bytes:
                raise MemoryStoreError(
                    f"cannot store memory entry of {size} bytes: it exceeds the "
                    f"configured maximum total size of {self._max_total_bytes} bytes"
                )

            self._make_room_for(size)

            new_id = entry_id or str(uuid.uuid4())
            ts = now_iso()
            self._state.execute(
                "INSERT INTO memory_entries "
                "(id, category, content, size_bytes, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (new_id, category, content, size, ts, ts),
            )
            entry = {
                "id": new_id,
                "category": category,
                "content": content,
                "size_bytes": size,
                "created_at": ts,
                "updated_at": ts,
            }
        LOGGER.debug("recorded memory entry %s (%d bytes)", new_id, size)
        return entry

    def _make_room_for(self, size: int) -> None:
        """Curate so that ``size`` more bytes fit within the bound.

        Called under ``self._lock``. With :data:`OVERFLOW_EVICT_OLDEST`, removes
        oldest entries until the new entry fits. With :data:`OVERFLOW_REJECT`,
        raises :class:`MemoryStoreError` if the entry would overflow the bound.
        """
        if self.total_size() + size <= self._max_total_bytes:
            return  # No curation needed.

        if self._on_overflow == OVERFLOW_REJECT:
            raise MemoryStoreError(
                f"cannot store memory entry of {size} bytes: it would exceed the "
                f"configured maximum total size of {self._max_total_bytes} bytes "
                f"(current usage {self.total_size()} bytes); curation rejected it"
            )

        # Evict oldest-first until there is room for the incoming entry.
        oldest_first = self._state.fetch_all(
            "SELECT id, size_bytes FROM memory_entries "
            "ORDER BY created_at ASC, id ASC"
        )
        for row in oldest_first:
            if self.total_size() + size <= self._max_total_bytes:
                break
            self._state.execute(
                "DELETE FROM memory_entries WHERE id = ?", (row["id"],)
            )
            LOGGER.debug("curated (evicted) memory entry %s", row["id"])

        # Defensive: with the per-entry oversize check in ``record`` this should
        # never trigger, but guard against an inconsistent store.
        if self.total_size() + size > self._max_total_bytes:
            raise MemoryStoreError(
                f"cannot store memory entry of {size} bytes after curation: "
                f"insufficient room within the configured maximum total size of "
                f"{self._max_total_bytes} bytes"
            )

    # -- listing (Requirement 11.4) -----------------------------------------

    def list_entries(self, category: str | None = None) -> list[dict[str, Any]]:
        """Return all current entries, optionally filtered by ``category``.

        Entries are ordered by creation time (then id) for a stable, reviewable
        listing (Requirement 11.4).
        """
        if category is None:
            rows = self._state.fetch_all(
                "SELECT id, category, content, size_bytes, created_at, updated_at "
                "FROM memory_entries ORDER BY created_at ASC, id ASC"
            )
        else:
            rows = self._state.fetch_all(
                "SELECT id, category, content, size_bytes, created_at, updated_at "
                "FROM memory_entries WHERE category = ? "
                "ORDER BY created_at ASC, id ASC",
                (category,),
            )
        return [dict(row) for row in rows]

    def get(self, entry_id: str) -> dict[str, Any] | None:
        """Return a single entry by id, or ``None`` if it does not exist."""
        row = self._state.fetch_one(
            "SELECT id, category, content, size_bytes, created_at, updated_at "
            "FROM memory_entries WHERE id = ?",
            (entry_id,),
        )
        return dict(row) if row is not None else None

    # -- deletion (Requirement 11.3) ----------------------------------------

    def delete(self, entry_id: str) -> None:
        """Remove an entry from persistence.

        Removal is performed directly and is not gated on any separate
        completion flag (Requirement 11.3): the row is deleted, then the
        deletion is verified by reading back. If the entry does not exist or the
        row is still present afterward, a descriptive :class:`MemoryStoreError` is
        raised so the failure is never silent.
        """
        with self._lock:
            existing = self.get(entry_id)
            if existing is None:
                raise MemoryStoreError(
                    f"cannot delete memory entry `{entry_id}`: no such entry"
                )

            try:
                self._state.execute(
                    "DELETE FROM memory_entries WHERE id = ?", (entry_id,)
                )
            except Exception as exc:  # noqa: BLE001 - surface as descriptive error
                raise MemoryStoreError(
                    f"cannot delete memory entry `{entry_id}`: {exc}"
                ) from exc

            # Verify removal independently of any completion flag.
            if self.get(entry_id) is not None:
                raise MemoryStoreError(
                    f"cannot delete memory entry `{entry_id}`: entry still present "
                    f"after deletion"
                )
        LOGGER.debug("deleted memory entry %s", entry_id)


def _resolve_max_bytes() -> int:
    """Resolve the configured max total size from the environment or default."""
    raw = os.environ.get("VLOOP_MEMORY_MAX_BYTES", "").strip()
    if not raw:
        return DEFAULT_MAX_TOTAL_BYTES
    try:
        value = int(raw)
    except ValueError:
        LOGGER.warning(
            "invalid VLOOP_MEMORY_MAX_BYTES=%r; using default %d",
            raw,
            DEFAULT_MAX_TOTAL_BYTES,
        )
        return DEFAULT_MAX_TOTAL_BYTES
    return value if value >= 0 else DEFAULT_MAX_TOTAL_BYTES
