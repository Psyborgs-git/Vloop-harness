import type { PendingApproval, WorkflowRun } from "../types";
import { requestJson } from "../api-client";

// Approval decisions go through the Control_Plane HTTP API only (Requirement
// 20.4): the Frontend never reaches the Approval_Manager or the kernel directly.
// These routes are mounted under the workflow-run resource (see
// control-plane/cp/handlers/approvals.py):
//   GET  /api/v1/workflow-runs/{runId}/approvals
//   POST /api/v1/workflow-runs/{runId}/approvals/{stepId}/approve
//   POST /api/v1/workflow-runs/{runId}/approvals/{stepId}/reject
const RUNS_BASE = "/api/v1/workflow-runs";

function approvalsBase(runId: string): string {
  return `${RUNS_BASE}/${encodeURIComponent(runId)}/approvals`;
}

/**
 * List the Approval_Checkpoints in a run currently awaiting a decision.
 *
 * The Control_Plane reconstructs these from persistence, so the list is
 * restart-safe (Requirement 8.5). Each entry carries the checkpoint context
 * that was streamed with the `approval.required` event (Requirement 8.2).
 */
export async function listPendingApprovals(
  runId: string,
): Promise<PendingApproval[]> {
  const payload = (await requestJson(approvalsBase(runId), "GET")) as {
    approvals?: PendingApproval[];
  };
  return payload.approvals ?? [];
}

/**
 * Approve a checkpoint and resume the run from it (Requirement 8.3).
 *
 * `edits` optionally carries user edits recorded as the checkpoint's output.
 */
export async function approveCheckpoint(
  runId: string,
  stepId: string,
  edits?: Record<string, unknown>,
): Promise<WorkflowRun> {
  const body = edits ? { edits } : {};
  const payload = (await requestJson(
    `${approvalsBase(runId)}/${encodeURIComponent(stepId)}/approve`,
    "POST",
    body,
  )) as { run: WorkflowRun };
  return payload.run;
}

/**
 * Reject a checkpoint, driving the run to the terminal `rejected` state and
 * skipping the checkpoint's dependents (Requirement 8.4).
 */
export async function rejectCheckpoint(
  runId: string,
  stepId: string,
  reason: string,
): Promise<WorkflowRun> {
  const payload = (await requestJson(
    `${approvalsBase(runId)}/${encodeURIComponent(stepId)}/reject`,
    "POST",
    { reason },
  )) as { run: WorkflowRun };
  return payload.run;
}
