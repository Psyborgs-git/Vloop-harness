"""Checkpoint_Manager — kernel-owned workspace snapshots and rollback.

The Checkpoint_Manager is the Control_Plane subsystem that protects a user's
files by requesting a Kernel snapshot of a sandbox workspace *before* any
filesystem mutation, and by requesting a Kernel restore when a rollback is
requested. It owns four responsibilities, each mapped to an acceptance
criterion of Requirement 13:

* **Snapshot before mutation (Requirement 13.1)** —
  :meth:`CheckpointManager.snapshot_before_mutation` asks the Kernel (through
  the injected execution manager) to snapshot the affected workspace and then
  records only the returned opaque snapshot reference plus metadata. The
  snapshot is taken before the caller performs the mutation.
* **Restore on rollback (Requirement 13.2)** —
  :meth:`CheckpointManager.restore` looks up a previously recorded checkpoint
  and asks the Kernel to restore the workspace to that checkpoint's snapshot.
* **Listing (Requirement 13.3)** —
  :meth:`CheckpointManager.list_checkpoints` returns the checkpoints recorded
  for a Workflow_Run so the Control_Plane can expose them to the user.
* **Kernel owns contents (Requirement 13.4)** — the Kernel owns and persists
  snapshot contents. The Control_Plane stores only metadata and the opaque
  ``kernel_snapshot_ref`` returned by the Kernel; it never stores snapshot file
  contents. A run with zero checkpoints is valid: listing simply returns an
  empty list and no snapshot contents are required to exist.

Persistence uses the schema declared in ``core/database.py``::

    checkpoints(id, run_id, workspace_id, kernel_snapshot_ref, created_at)

The execution manager is injected and duck-typed: any object exposing
``snapshot_workspace(workspace_id) -> snapshot_ref`` and
``restore_workspace(workspace_id, snap) -> None`` works. In production this is
:class:`~adapters.rust_infra.RustInfraExecutionManager`, which forwards to the
Kernel's ``FilesystemControl.Snapshot``/``.Restore`` RPCs and returns only the
opaque snapshot reference (Req 13.4).

Identifiers are UUID4 strings and timestamps come from ``core.helpers.now_iso``,
matching the conventions used by the other Control_Plane services.
"""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Any, Protocol

from core.database import DatabaseBackend
from core.helpers import now_iso

LOGGER = logging.getLogger("vloop.control_plane.checkpoint_manager")


class CheckpointManagerError(Exception):
    """Raised when a Checkpoint_Manager operation cannot be completed.

    Carries a human-readable message describing why the operation failed (for
    example, a rollback request for a checkpoint that does not exist, or a
    Kernel snapshot that returned no reference).
    """


class SupportsWorkspaceSnapshots(Protocol):
    """Duck-typed kernel execution surface the Checkpoint_Manager depends on.

    The Kernel owns snapshot storage; these methods return/consume only the
    opaque snapshot reference, never file contents (Req 13.4).
    """

    def snapshot_workspace(self, workspace_id: str) -> str: ...

    def restore_workspace(self, workspace_id: str, snap: str) -> None: ...


class CheckpointManager:
    """Requests kernel snapshots/restores and records only metadata.

    Thread-safe: a single re-entrant lock serializes the snapshot-then-record
    and lookup-then-restore sequences so concurrent callers cannot interleave a
    record with a restore against stale state.

    :param state: the shared :class:`DatabaseBackend`.
    :param execution_manager: a kernel-backed execution manager exposing
        ``snapshot_workspace`` and ``restore_workspace`` (in production,
        :class:`~adapters.rust_infra.RustInfraExecutionManager`).
    """

    def __init__(
        self,
        state: DatabaseBackend,
        execution_manager: SupportsWorkspaceSnapshots,
    ) -> None:
        if state is None:
            raise ValueError("a DatabaseBackend is required")
        if execution_manager is None:
            raise ValueError("an execution manager is required")
        if not hasattr(execution_manager, "snapshot_workspace") or not hasattr(
            execution_manager, "restore_workspace"
        ):
            raise TypeError(
                "execution_manager must expose snapshot_workspace and "
                "restore_workspace"
            )
        self._state = state
        self._exec = execution_manager
        self._lock = threading.RLock()

    # -- snapshot before mutation (Requirement 13.1) ------------------------

    def snapshot_before_mutation(
        self,
        run_id: str,
        workspace_id: str,
        checkpoint_id: str | None = None,
    ) -> dict[str, Any]:
        """Snapshot a workspace via the Kernel before a mutation and record it.

        Requests a Kernel snapshot of ``workspace_id`` and records a checkpoint
        row holding only the run/workspace metadata and the opaque snapshot
        reference returned by the Kernel (Req 13.1, 13.4). The snapshot is taken
        before the caller performs the mutation. Returns the recorded checkpoint
        as a dict.

        Raises :class:`CheckpointManagerError` if the Kernel returns no usable
        snapshot reference, so a checkpoint is never recorded without a real
        kernel-owned snapshot behind it.
        """
        if not run_id:
            raise ValueError("run_id is required to record a checkpoint")
        if not workspace_id:
            raise ValueError("workspace_id is required to snapshot a workspace")

        with self._lock:
            # Ask the Kernel to take the snapshot first; the Kernel owns and
            # persists the contents and returns only an opaque reference.
            try:
                snapshot_ref = self._exec.snapshot_workspace(workspace_id)
            except Exception as exc:  # noqa: BLE001 - surface as descriptive error
                raise CheckpointManagerError(
                    f"cannot snapshot workspace `{workspace_id}` for run "
                    f"`{run_id}`: {exc}"
                ) from exc

            if not snapshot_ref or not isinstance(snapshot_ref, str):
                raise CheckpointManagerError(
                    f"cannot record checkpoint for run `{run_id}`: the Kernel "
                    f"returned no snapshot reference for workspace "
                    f"`{workspace_id}`"
                )

            new_id = checkpoint_id or str(uuid.uuid4())
            ts = now_iso()
            # Store metadata and the opaque reference only — never file contents
            # (Req 13.4).
            self._state.execute(
                "INSERT INTO checkpoints "
                "(id, run_id, workspace_id, kernel_snapshot_ref, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (new_id, run_id, workspace_id, snapshot_ref, ts),
            )
            checkpoint = {
                "id": new_id,
                "run_id": run_id,
                "workspace_id": workspace_id,
                "kernel_snapshot_ref": snapshot_ref,
                "created_at": ts,
            }
        LOGGER.debug(
            "recorded checkpoint %s for run %s (workspace %s)",
            new_id,
            run_id,
            workspace_id,
        )
        return checkpoint

    # -- restore on rollback (Requirement 13.2) -----------------------------

    def restore(self, checkpoint_id: str) -> dict[str, Any]:
        """Request that the Kernel restore the workspace to a checkpoint.

        Looks up the recorded checkpoint and asks the Kernel to restore the
        workspace to that checkpoint's snapshot reference (Req 13.2). The Kernel
        performs the actual restore from contents it owns; the Control_Plane
        only supplies the opaque reference. Returns the checkpoint that was
        restored.

        Raises :class:`CheckpointManagerError` if the checkpoint does not exist
        or the Kernel restore fails.
        """
        if not checkpoint_id:
            raise ValueError("checkpoint_id is required to restore a checkpoint")

        with self._lock:
            checkpoint = self.get(checkpoint_id)
            if checkpoint is None:
                raise CheckpointManagerError(
                    f"cannot restore checkpoint `{checkpoint_id}`: no such "
                    f"checkpoint"
                )

            try:
                self._exec.restore_workspace(
                    checkpoint["workspace_id"],
                    checkpoint["kernel_snapshot_ref"],
                )
            except Exception as exc:  # noqa: BLE001 - surface as descriptive error
                raise CheckpointManagerError(
                    f"cannot restore checkpoint `{checkpoint_id}` for workspace "
                    f"`{checkpoint['workspace_id']}`: {exc}"
                ) from exc
        LOGGER.debug(
            "restored checkpoint %s (workspace %s)",
            checkpoint_id,
            checkpoint["workspace_id"],
        )
        return checkpoint

    # -- listing (Requirement 13.3) -----------------------------------------

    def list_checkpoints(self, run_id: str) -> list[dict[str, Any]]:
        """Return the checkpoints recorded for a Workflow_Run.

        Checkpoints are ordered by creation time (then id) for a stable,
        reviewable listing (Req 13.3). A run with no checkpoints yields an empty
        list, which is a valid configuration (Req 13.4).
        """
        if not run_id:
            raise ValueError("run_id is required to list checkpoints")
        rows = self._state.fetch_all(
            "SELECT id, run_id, workspace_id, kernel_snapshot_ref, created_at "
            "FROM checkpoints WHERE run_id = ? "
            "ORDER BY created_at ASC, id ASC",
            (run_id,),
        )
        return [dict(row) for row in rows]

    def get(self, checkpoint_id: str) -> dict[str, Any] | None:
        """Return a single checkpoint by id, or ``None`` if it does not exist."""
        if not checkpoint_id:
            return None
        row = self._state.fetch_one(
            "SELECT id, run_id, workspace_id, kernel_snapshot_ref, created_at "
            "FROM checkpoints WHERE id = ?",
            (checkpoint_id,),
        )
        return dict(row) if row is not None else None
