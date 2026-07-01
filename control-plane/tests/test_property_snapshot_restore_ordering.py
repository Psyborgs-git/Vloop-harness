"""Property-based test for Checkpoint_Manager snapshot/restore ordering.

# Feature: orchestration-engine-completion, Property 32: Snapshot precedes mutation and restore targets the chosen checkpoint

Property 32 states two things about the Checkpoint_Manager's interaction with
the Kernel:

* **Snapshot precedes mutation (Requirement 13.1)** — for any sequence of
  "snapshot-before-mutation then mutate" operations, each Kernel
  ``snapshot_workspace`` call is observed *before* its corresponding mutation.
  The Checkpoint_Manager protects a user's files by snapshotting first.
* **Restore targets the chosen checkpoint (Requirement 13.2)** — calling
  :meth:`CheckpointManager.restore` with a chosen ``checkpoint_id`` invokes the
  Kernel ``restore_workspace`` with exactly that checkpoint's ``workspace_id``
  and ``kernel_snapshot_ref`` — never another checkpoint's.

The test uses a fake execution manager that records, in a single ordered log,
every ``snapshot_workspace`` and ``restore_workspace`` call. The mutation step
is a callback that appends a ``mutate`` marker to the same log, so the relative
order of "snapshot" and "mutate" events is directly observable. A real
temporary SQLite backend persists the recorded checkpoints, matching production
persistence semantics.

**Validates: Requirements 13.1, 13.2**
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import uuid

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.checkpoint_manager import CheckpointManager
from core.database import SQLiteBackend

# ---------------------------------------------------------------------------
# Fake kernel execution manager
# ---------------------------------------------------------------------------


class _RecordingExecutionManager:
    """Fake kernel surface recording snapshot/restore call order.

    Mirrors the duck-typed contract the Checkpoint_Manager depends on:
    ``snapshot_workspace(workspace_id) -> ref`` and
    ``restore_workspace(workspace_id, snap) -> None``. Every call is appended to
    a shared ordered ``events`` log so the test can assert relative ordering
    against mutation markers. Each snapshot returns a unique opaque reference,
    exactly as the Kernel would (the Control_Plane never sees file contents).
    """

    def __init__(self) -> None:
        self.events: list[tuple] = []
        self._counter = 0
        self.snapshot_calls: list[tuple[str, str]] = []
        self.restore_calls: list[tuple[str, str]] = []

    def snapshot_workspace(self, workspace_id: str) -> str:
        self._counter += 1
        ref = f"kernel-snap-{self._counter}-{uuid.uuid4().hex[:8]}"
        self.events.append(("snapshot", workspace_id, ref))
        self.snapshot_calls.append((workspace_id, ref))
        return ref

    def restore_workspace(self, workspace_id: str, snap: str) -> None:
        self.events.append(("restore", workspace_id, snap))
        self.restore_calls.append((workspace_id, snap))


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Workspace identifiers are arbitrary non-empty tokens; repeats are allowed so
# the property holds even when several operations target the same workspace.
_workspace_ids = st.text(
    alphabet=st.characters(min_codepoint=33, max_codepoint=126),
    min_size=1,
    max_size=16,
)


@st.composite
def operation_plans(draw: st.DrawFn) -> tuple[list[str], int]:
    """Generate a sequence of mutation workspaces plus a chosen checkpoint index.

    Returns ``(workspace_ids, chosen_index)`` where ``workspace_ids`` is the
    ordered list of workspaces to snapshot-then-mutate, and ``chosen_index``
    selects which of the resulting checkpoints to later restore.
    """
    workspaces = draw(st.lists(_workspace_ids, min_size=1, max_size=8))
    chosen_index = draw(st.integers(min_value=0, max_value=len(workspaces) - 1))
    return workspaces, chosen_index


# ---------------------------------------------------------------------------
# Property 32: Snapshot precedes mutation and restore targets the chosen checkpoint
# ---------------------------------------------------------------------------


# ``deadline=None``: each example performs real SQLite disk I/O (a temp file and
# a CheckpointManager/SQLiteBackend construction), so per-example timings vary
# and are not a meaningful signal for this ordering property.
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(plan=operation_plans())
def test_snapshot_precedes_mutation_and_restore_targets_chosen(
    plan: tuple[list[str], int],
) -> None:
    """Each snapshot precedes its mutation; restore targets the chosen checkpoint."""
    workspaces, chosen_index = plan

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "checkpoint-prop.db"
        infra = _RecordingExecutionManager()
        manager = CheckpointManager(SQLiteBackend(db_path), infra)
        run_id = f"run-{uuid.uuid4().hex[:12]}"

        recorded: list[dict] = []
        for op_index, workspace_id in enumerate(workspaces):
            # Snapshot-before-mutation: the manager asks the Kernel to snapshot,
            # then the caller performs the mutation (recorded as a marker).
            checkpoint = manager.snapshot_before_mutation(run_id, workspace_id)
            recorded.append(checkpoint)
            infra.events.append(("mutate", op_index, workspace_id))

        # Req 13.1: each snapshot call must precede its corresponding mutation.
        # Operations are serial, so the i-th snapshot event pairs with the i-th
        # mutate event; assert the snapshot appears earlier in the ordered log.
        snapshot_positions = [
            i for i, e in enumerate(infra.events) if e[0] == "snapshot"
        ]
        mutate_positions = [
            i for i, e in enumerate(infra.events) if e[0] == "mutate"
        ]
        assert len(snapshot_positions) == len(workspaces)
        assert len(mutate_positions) == len(workspaces)
        for snap_pos, mut_pos in zip(snapshot_positions, mutate_positions):
            assert snap_pos < mut_pos

        # Each recorded checkpoint stores exactly the opaque reference the Kernel
        # returned for that workspace, in order.
        for checkpoint, (ws, ref) in zip(recorded, infra.snapshot_calls):
            assert checkpoint["workspace_id"] == ws
            assert checkpoint["kernel_snapshot_ref"] == ref

        # Req 13.2: restoring the chosen checkpoint must call restore_workspace
        # with exactly that checkpoint's workspace_id and kernel_snapshot_ref.
        chosen = recorded[chosen_index]
        infra.restore_calls.clear()
        restored = manager.restore(chosen["id"])

        assert restored["id"] == chosen["id"]
        assert infra.restore_calls == [
            (chosen["workspace_id"], chosen["kernel_snapshot_ref"])
        ]
