import type { ScheduledTask, ScheduledTaskState } from "../types";
import { requestJson } from "../api-client";

// Scheduled-task create/pause/resume/list go through the Control_Plane HTTP API
// only (Requirement 20.4): the Frontend never touches the Scheduler directly.
// These routes are defined in control-plane/cp/handlers/schedules.py:
//   GET  /api/v1/schedules                 (optional ?definitionId=)  (Req 14.1)
//   POST /api/v1/schedules                 {definitionId, cronExpression, state?} (Req 14.1)
//   POST /api/v1/schedules/{id}/pause                                  (Req 14.3)
//   POST /api/v1/schedules/{id}/resume                                 (Req 14.3)
// An invalid cron expression is rejected by the Control_Plane with a 400 whose
// message is surfaced to the user by the view.
const SCHEDULES_BASE = "/api/v1/schedules";

export interface CreateScheduledTaskInput {
  definitionId: string;
  cronExpression: string;
  state?: ScheduledTaskState;
}

/**
 * List Scheduled_Tasks (Requirement 14.1). When `definitionId` is provided the
 * Control_Plane filters to schedules for that workflow definition; otherwise it
 * returns every schedule ordered by creation time.
 */
export async function listScheduledTasks(
  definitionId?: string,
): Promise<ScheduledTask[]> {
  const suffix = definitionId
    ? `?definitionId=${encodeURIComponent(definitionId)}`
    : "";
  const payload = (await requestJson(
    `${SCHEDULES_BASE}${suffix}`,
    "GET",
  )) as { scheduledTasks?: ScheduledTask[] };
  return payload.scheduledTasks ?? [];
}

/**
 * Create a Scheduled_Task in either an `active` or `paused` state
 * (Requirement 14.1). The Control_Plane validates the cron expression and
 * rejects an invalid one with a 400.
 */
export async function createScheduledTask(
  input: CreateScheduledTaskInput,
): Promise<ScheduledTask> {
  const body: Record<string, unknown> = {
    definitionId: input.definitionId,
    cronExpression: input.cronExpression,
  };
  if (input.state) {
    body.state = input.state;
  }
  const payload = (await requestJson(SCHEDULES_BASE, "POST", body)) as {
    scheduledTask: ScheduledTask;
  };
  return payload.scheduledTask;
}

/** Pause a Scheduled_Task so it stops triggering runs (Requirement 14.3). */
export async function pauseScheduledTask(
  taskId: string,
): Promise<ScheduledTask> {
  const payload = (await requestJson(
    `${SCHEDULES_BASE}/${encodeURIComponent(taskId)}/pause`,
    "POST",
  )) as { scheduledTask: ScheduledTask };
  return payload.scheduledTask;
}

/** Resume a paused Scheduled_Task so it can trigger runs again (Req 14.3). */
export async function resumeScheduledTask(
  taskId: string,
): Promise<ScheduledTask> {
  const payload = (await requestJson(
    `${SCHEDULES_BASE}/${encodeURIComponent(taskId)}/resume`,
    "POST",
  )) as { scheduledTask: ScheduledTask };
  return payload.scheduledTask;
}
