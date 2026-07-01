"""Example-based unit tests for Checkpoint_Manager listing (`core/checkpoint_manager.py`).

Covers task 24.4 with concrete examples for Requirement 13.3:

    THE Control_Plane SHALL expose an API that lists the Checkpoints available
    for a Workflow_Run.

:meth:`CheckpointManager.list_checkpoints` is the method backing that API. These
tests verify, with worked examples rather than properties:

* ``list_checkpoints`` returns every checkpoint recorded for a run, in creation
  order (Req 13.3).
* Results are filtered by ``run_id`` — checkpoints belonging to other runs are
  excluded (Req 13.3).
* A run with no recorded checkpoints lists as ``[]`` (a valid, zero-checkpoint
  configuration, Req 13.4).
* Each listed entry exposes the full checkpoint shape: ``id``, ``run_id``,
  ``workspace_id``, ``kernel_snapshot_ref``, and ``created_at`` (Req 13.3).

Checkpoints are recorded through :meth:`snapshot_before_mutation`, exactly as
production does. A real temporary SQLite backend persists the rows, and a fake
execution manager stands in for the Kernel, returning a distinct opaque
snapshot reference for each call (the Control_Plane never sees file contents).

**Validates: Requirements 13.3**
"""

from __future__ import annotations

from pathlib import Path
import tempfile

import pytest

import core.checkpoint_manager as checkpoint_manager_module
from core.checkpoint_manager import CheckpointManager
from core.database import SQLiteBackend


# ---------------------------------------------------------------------------
# Fake kernel execution manager
# ---------------------------------------------------------------------------


class _FakeExecutionManager:
    """Fake Kernel surface returning a distinct snapshot ref per call.

    Mirrors the duck-typed contract the Checkpoint_Manager depends on:
    ``snapshot_workspace(workspace_id) -> ref`` and
    ``restore_workspace(workspace_id, snap) -> None``. Each snapshot returns a
    unique opaque reference, exactly as the Kernel would — the Control_Plane
    stores only that reference, never file contents (Req 13.4).
    """

    def __init__(self) -> None:
        self._counter = 0
        self.snapshot_calls: list[str] = []

    def snapshot_workspace(self, workspace_id: str) -> str:
        self._counter += 1
        self.snapshot_calls.append(workspace_id)
        return f"kernel-snap-{self._counter}"

    def restore_workspace(self, workspace_id: str, snap: str) -> None:  # pragma: no cover - unused here
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def manager(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CheckpointManager:
    """A CheckpointManager backed by a real temp SQLite DB and a fake Kernel.

    ``now_iso`` is patched to a monotonically increasing clock so each recorded
    checkpoint gets a strictly later, distinct ``created_at``. This makes the
    creation-order assertions deterministic without relying on wall-clock
    resolution (rapid inserts could otherwise share a timestamp).
    """
    db_path = tmp_path / "checkpoints.db"
    backend = SQLiteBackend(db_path)

    ticks = iter(range(1, 100_000))

    def _fake_now_iso() -> str:
        # Zero-padded so lexical ordering matches chronological ordering.
        return f"2024-01-01T00:00:{next(ticks):05d}Z"

    monkeypatch.setattr(checkpoint_manager_module, "now_iso", _fake_now_iso)

    return CheckpointManager(backend, _FakeExecutionManager())


# ---------------------------------------------------------------------------
# Req 13.3: listing returns all checkpoints for a run, in creation order
# ---------------------------------------------------------------------------


def test_lists_all_checkpoints_for_a_run_in_creation_order(
    manager: CheckpointManager,
) -> None:
    """Every checkpoint recorded for a run is listed in the order it was created."""
    first = manager.snapshot_before_mutation("run-A", "ws-1")
    second = manager.snapshot_before_mutation("run-A", "ws-2")
    third = manager.snapshot_before_mutation("run-A", "ws-3")

    listed = manager.list_checkpoints("run-A")

    assert [c["id"] for c in listed] == [first["id"], second["id"], third["id"]]
    # created_at values are strictly increasing in the listed order.
    timestamps = [c["created_at"] for c in listed]
    assert timestamps == sorted(timestamps)
    assert len(set(timestamps)) == 3


def test_repeated_workspace_records_distinct_checkpoints(
    manager: CheckpointManager,
) -> None:
    """Snapshotting the same workspace twice yields two distinct ordered entries."""
    first = manager.snapshot_before_mutation("run-A", "ws-1")
    second = manager.snapshot_before_mutation("run-A", "ws-1")

    listed = manager.list_checkpoints("run-A")

    assert [c["id"] for c in listed] == [first["id"], second["id"]]
    assert first["id"] != second["id"]
    # Each got its own opaque kernel snapshot reference.
    assert first["kernel_snapshot_ref"] != second["kernel_snapshot_ref"]


# ---------------------------------------------------------------------------
# Req 13.3: listing is filtered by run_id
# ---------------------------------------------------------------------------


def test_listing_filters_by_run_id_excluding_other_runs(
    manager: CheckpointManager,
) -> None:
    """Only the requested run's checkpoints are returned; other runs are excluded."""
    a1 = manager.snapshot_before_mutation("run-A", "ws-1")
    b1 = manager.snapshot_before_mutation("run-B", "ws-9")
    a2 = manager.snapshot_before_mutation("run-A", "ws-2")
    b2 = manager.snapshot_before_mutation("run-B", "ws-8")

    listed_a = manager.list_checkpoints("run-A")
    listed_b = manager.list_checkpoints("run-B")

    assert [c["id"] for c in listed_a] == [a1["id"], a2["id"]]
    assert [c["id"] for c in listed_b] == [b1["id"], b2["id"]]
    # Cross-run leakage check: no run-B id appears in run-A's listing.
    assert {c["run_id"] for c in listed_a} == {"run-A"}
    assert {c["run_id"] for c in listed_b} == {"run-B"}


# ---------------------------------------------------------------------------
# Req 13.4: a run with no checkpoints lists as []
# ---------------------------------------------------------------------------


def test_run_with_no_checkpoints_lists_empty(manager: CheckpointManager) -> None:
    """A run that has never recorded a checkpoint yields an empty list."""
    assert manager.list_checkpoints("run-never-touched") == []


def test_unrelated_run_still_lists_empty_when_other_runs_exist(
    manager: CheckpointManager,
) -> None:
    """Recording for one run does not make another run's listing non-empty."""
    manager.snapshot_before_mutation("run-A", "ws-1")

    assert manager.list_checkpoints("run-B") == []


# ---------------------------------------------------------------------------
# Req 13.3: each listed entry exposes the full checkpoint shape
# ---------------------------------------------------------------------------


def test_listed_entry_exposes_full_checkpoint_shape(
    manager: CheckpointManager,
) -> None:
    """Each listed checkpoint exposes id/run_id/workspace_id/kernel_snapshot_ref/created_at."""
    recorded = manager.snapshot_before_mutation("run-A", "ws-1")

    (entry,) = manager.list_checkpoints("run-A")

    assert set(entry.keys()) == {
        "id",
        "run_id",
        "workspace_id",
        "kernel_snapshot_ref",
        "created_at",
    }
    # The listed values match what was recorded.
    assert entry["id"] == recorded["id"]
    assert entry["run_id"] == "run-A"
    assert entry["workspace_id"] == "ws-1"
    assert entry["kernel_snapshot_ref"] == recorded["kernel_snapshot_ref"]
    assert entry["created_at"] == recorded["created_at"]
    # The opaque reference is a non-empty string (the only contents CP stores).
    assert isinstance(entry["kernel_snapshot_ref"], str)
    assert entry["kernel_snapshot_ref"]


def test_empty_run_id_is_rejected(manager: CheckpointManager) -> None:
    """Listing requires a run_id; an empty run_id is a programming error."""
    with pytest.raises(ValueError):
        manager.list_checkpoints("")
