import type { Checkpoint } from "../types";
import { requestJson } from "../api-client";

// Checkpoint listing + rollback go through the Control_Plane HTTP API only
// (Requirement 20.4): the Frontend never reaches the Checkpoint_Manager or the
// kernel directly. These routes are defined in
// control-plane/cp/handlers/checkpoints.py:
//   GET  /api/v1/runs/{runId}/checkpoints          (Requirement 13.3)
//   POST /api/v1/checkpoints/{checkpointId}/rollback (Requirement 13.2)
const RUNS_BASE = "/api/v1/runs";
const CHECKPOINTS_BASE = "/api/v1/checkpoints";

/**
 * List the Checkpoints recorded for a Workflow_Run (Requirement 13.3).
 *
 * The Control_Plane returns them ordered by creation time for a stable,
 * reviewable listing. A run with no checkpoints yields an empty list.
 */
export async function listCheckpoints(runId: string): Promise<Checkpoint[]> {
  const payload = (await requestJson(
    `${RUNS_BASE}/${encodeURIComponent(runId)}/checkpoints`,
    "GET",
  )) as { checkpoints?: Checkpoint[]; runId?: string };
  return payload.checkpoints ?? [];
}

/**
 * Request that the Kernel restore the workspace to a Checkpoint's snapshot
 * (Requirement 13.2). Returns the checkpoint that was restored.
 */
export async function rollbackCheckpoint(
  checkpointId: string,
): Promise<Checkpoint> {
  const payload = (await requestJson(
    `${CHECKPOINTS_BASE}/${encodeURIComponent(checkpointId)}/rollback`,
    "POST",
  )) as { checkpoint: Checkpoint };
  return payload.checkpoint;
}
