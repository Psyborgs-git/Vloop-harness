"""Property-based test for kernel-owned checkpoint contents.

# Feature: orchestration-engine-completion, Property 33: Kernel owns checkpoint contents; Control_Plane stores only references

Property 33 states that for any sequence of checkpoint operations, Control_Plane
state contains only checkpoint *metadata* and the opaque kernel *snapshot
reference*, and never the underlying snapshot file contents. A configuration
with zero checkpoints and no snapshot contents is a valid state.

The :class:`~core.checkpoint_manager.CheckpointManager` requests a snapshot from
the Kernel (modelled here by :class:`FakeKernelFilesystem`) and records only
what the Kernel hands back: an opaque ``kernel_snapshot_ref``. The Kernel is the
sole owner of the file-content blobs; it keeps them in its own store and returns
*only* the opaque reference. This test asserts that, after any number of
``snapshot_before_mutation`` calls:

* the persisted ``checkpoints`` table has exactly the metadata + reference
  columns ``{id, run_id, workspace_id, kernel_snapshot_ref, created_at}`` and no
  column that could hold file contents; and
* the kernel-owned content blob for each workspace never appears verbatim in any
  Control_Plane-persisted column value (it lives only in the Kernel's store);
  and
* a run that performed zero snapshots lists an empty set of checkpoints, which
  is a valid zero-checkpoint state requiring no snapshot contents.

**Validates: Requirements 13.4**
"""

from __future__ import annotations

import sqlite3
import tempfile
import uuid
from pathlib import Path
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.checkpoint_manager import CheckpointManager
from core.database import SQLiteBackend

# ---------------------------------------------------------------------------
# Fake Kernel: the sole owner of snapshot file contents.
# ---------------------------------------------------------------------------

# A sentinel embedded in every kernel-owned content blob. It cannot collide with
# the generated run/workspace identifiers (which are constrained below), so if it
# ever shows up in a persisted Control_Plane column the property has been
# violated for real rather than by accidental coincidence.
_CONTENT_SENTINEL = "KERNEL-OWNED-CONTENT::"


class FakeKernelFilesystem:
    """Stand-in for the Kernel's ``FilesystemControl`` snapshot/restore surface.

    Mirrors the contract honoured by
    :class:`~adapters.rust_infra.RustInfraExecutionManager`: the Kernel takes a
    snapshot, *keeps the file contents in its own store*, and returns only an
    opaque reference. The opaque reference is a fresh UUID that is in no way
    derived from the contents, so the Control_Plane never receives the contents.
    """

    def __init__(self, contents_by_workspace: dict[str, str]) -> None:
        # The contents the Kernel "owns" for each workspace.
        self._contents_by_workspace = dict(contents_by_workspace)
        # ref -> contents, the Kernel's private snapshot store. The Control_Plane
        # never sees this mapping.
        self.owned_snapshots: dict[str, str] = {}

    def snapshot_workspace(self, workspace_id: str) -> str:
        contents = self._contents_by_workspace.get(workspace_id, "")
        ref = f"ksnap-{uuid.uuid4()}"
        # Kernel persists the contents privately and hands back only the ref.
        self.owned_snapshots[ref] = contents
        return ref

    def restore_workspace(self, workspace_id: str, snap: str) -> None:  # pragma: no cover - not exercised here
        # Restore is driven purely by the opaque ref; contents stay kernel-side.
        _ = self.owned_snapshots.get(snap)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Identifiers are constrained to characters that cannot reproduce the content
# sentinel, keeping the "contents never appear in a persisted column" assertion
# a meaningful signal rather than vulnerable to accidental substring overlap.
_id_text = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="-_"),
    min_size=1,
    max_size=16,
)


@st.composite
def checkpoint_operations(draw: st.DrawFn) -> tuple[list[dict[str, str]], dict[str, str]]:
    """Generate a sequence of snapshot requests plus the kernel-owned contents.

    Returns ``(operations, contents_by_workspace)`` where each operation is a
    ``{"run_id", "workspace_id"}`` dict and ``contents_by_workspace`` maps each
    workspace to a distinctive, sentinel-bearing content blob that the Kernel
    owns. Empty sequences are allowed so the zero-checkpoint state is exercised.
    """
    n = draw(st.integers(min_value=0, max_value=20))
    operations: list[dict[str, str]] = []
    contents_by_workspace: dict[str, str] = {}
    for _ in range(n):
        run_id = draw(_id_text)
        workspace_id = draw(_id_text)
        # A fake file-content blob the kernel "owns". The sentinel guarantees the
        # blob is identifiable wherever it might leak.
        blob = _CONTENT_SENTINEL + draw(st.text(min_size=0, max_size=80))
        operations.append({"run_id": run_id, "workspace_id": workspace_id})
        contents_by_workspace[workspace_id] = blob
    return operations, contents_by_workspace


# ---------------------------------------------------------------------------
# Property 33: Kernel owns checkpoint contents; CP stores only references
# ---------------------------------------------------------------------------


# ``deadline=None``: every example performs real SQLite disk I/O against a temp
# file, so per-example timings vary and are not a meaningful signal here.
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(scenario=checkpoint_operations())
def test_kernel_owns_checkpoint_contents(
    scenario: tuple[list[dict[str, str]], dict[str, str]],
) -> None:
    """CP persists only metadata + the opaque ref; contents stay kernel-owned."""
    operations, contents_by_workspace = scenario

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "checkpoints-prop.db"
        backend = SQLiteBackend(db_path)
        kernel = FakeKernelFilesystem(contents_by_workspace)
        manager = CheckpointManager(backend, kernel)

        recorded: list[dict[str, Any]] = []
        for op in operations:
            recorded.append(
                manager.snapshot_before_mutation(op["run_id"], op["workspace_id"])
            )

        # --- The CP returned only metadata + the opaque reference. ---------
        for checkpoint in recorded:
            assert set(checkpoint) == {
                "id",
                "run_id",
                "workspace_id",
                "kernel_snapshot_ref",
                "created_at",
            }
            # The reference is the opaque kernel-owned handle, not the contents.
            assert checkpoint["kernel_snapshot_ref"] in kernel.owned_snapshots
            for value in checkpoint.values():
                assert _CONTENT_SENTINEL not in str(value)

        # --- The persisted schema has no column that could hold contents. --
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(checkpoints)").fetchall()
            }
            assert columns == {
                "id",
                "run_id",
                "workspace_id",
                "kernel_snapshot_ref",
                "created_at",
            }

            # --- No kernel-owned content blob leaks into ANY persisted cell. -
            rows = conn.execute(
                "SELECT id, run_id, workspace_id, kernel_snapshot_ref, created_at "
                "FROM checkpoints"
            ).fetchall()
            assert len(rows) == len(operations)
            for row in rows:
                for value in tuple(row):
                    assert _CONTENT_SENTINEL not in str(value)
                # The stored reference must be one the Kernel actually owns.
                assert row["kernel_snapshot_ref"] in kernel.owned_snapshots

        # --- Cross-check via the CheckpointManager listing API. ------------
        for run_id in {op["run_id"] for op in operations}:
            listed = manager.list_checkpoints(run_id)
            expected = sum(1 for op in operations if op["run_id"] == run_id)
            assert len(listed) == expected
            for checkpoint in listed:
                assert set(checkpoint) == {
                    "id",
                    "run_id",
                    "workspace_id",
                    "kernel_snapshot_ref",
                    "created_at",
                }
                for value in checkpoint.values():
                    assert _CONTENT_SENTINEL not in str(value)

        # --- Zero-checkpoint state is valid: an untouched run lists empty. -
        unseen_run = "run-with-no-checkpoints-" + uuid.uuid4().hex
        assert manager.list_checkpoints(unseen_run) == []
