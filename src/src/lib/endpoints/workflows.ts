import type {
  WorkflowDefinition,
  WorkflowRun,
  WorkflowRunObservation,
  WorkflowTemplate,
  WorkflowValidationResult,
} from "../types";
import { requestJson } from "../api-client";

// All workflow definition + run lifecycle goes through the Control_Plane HTTP
// API only (Requirement 20.4): no direct kernel/db access from the Frontend.
const WORKFLOWS_BASE = "/api/v1/workflows";
const RUNS_BASE = "/api/v1/workflow-runs";

// -- Definitions & validation ----------------------------------------------

export async function listWorkflows(): Promise<WorkflowDefinition[]> {
  const payload = (await requestJson(WORKFLOWS_BASE, "GET")) as {
    workflows?: WorkflowDefinition[];
  };
  return payload.workflows ?? [];
}

export async function getWorkflow(
  workflowId: string,
): Promise<WorkflowDefinition> {
  const payload = (await requestJson(
    `${WORKFLOWS_BASE}/${encodeURIComponent(workflowId)}`,
    "GET",
  )) as { workflow: WorkflowDefinition };
  return payload.workflow;
}

export async function createWorkflow(
  definition: Record<string, unknown>,
): Promise<WorkflowDefinition> {
  const payload = (await requestJson(WORKFLOWS_BASE, "POST", definition)) as {
    workflow: WorkflowDefinition;
  };
  return payload.workflow;
}

export async function validateWorkflow(
  definition: Record<string, unknown>,
): Promise<WorkflowValidationResult> {
  return (await requestJson(
    `${WORKFLOWS_BASE}/validate`,
    "POST",
    definition,
  )) as WorkflowValidationResult;
}

// -- Templates --------------------------------------------------------------

export async function listWorkflowTemplates(): Promise<WorkflowTemplate[]> {
  const payload = (await requestJson(
    `${WORKFLOWS_BASE}/templates`,
    "GET",
  )) as { workflowTemplates?: WorkflowTemplate[] };
  return payload.workflowTemplates ?? [];
}

export async function getWorkflowTemplate(
  templateId: string,
): Promise<WorkflowTemplate> {
  const payload = (await requestJson(
    `${WORKFLOWS_BASE}/templates/${encodeURIComponent(templateId)}`,
    "GET",
  )) as { workflowTemplate: WorkflowTemplate };
  return payload.workflowTemplate;
}

export async function instantiateWorkflowTemplate(
  templateId: string,
  overrides: Record<string, unknown> = {},
): Promise<WorkflowDefinition> {
  const payload = (await requestJson(
    `${WORKFLOWS_BASE}/templates/${encodeURIComponent(templateId)}`,
    "POST",
    overrides,
  )) as { workflow: WorkflowDefinition };
  return payload.workflow;
}

// -- Runs -------------------------------------------------------------------

export async function startWorkflowRun(
  workflowId: string,
  body: Record<string, unknown> = {},
): Promise<WorkflowRun> {
  const payload = (await requestJson(
    `${WORKFLOWS_BASE}/${encodeURIComponent(workflowId)}/runs`,
    "POST",
    body,
  )) as { run: WorkflowRun };
  return payload.run;
}

export async function listWorkflowRuns(
  workflowId: string,
): Promise<WorkflowRun[]> {
  const payload = (await requestJson(
    `${WORKFLOWS_BASE}/${encodeURIComponent(workflowId)}/runs`,
    "GET",
  )) as { runs?: WorkflowRun[] };
  return payload.runs ?? [];
}

export async function getWorkflowRun(
  runId: string,
): Promise<WorkflowRunObservation> {
  return (await requestJson(
    `${RUNS_BASE}/${encodeURIComponent(runId)}`,
    "GET",
  )) as WorkflowRunObservation;
}

export async function cancelWorkflowRun(runId: string): Promise<WorkflowRun> {
  const payload = (await requestJson(
    `${RUNS_BASE}/${encodeURIComponent(runId)}/cancel`,
    "POST",
  )) as { run: WorkflowRun };
  return payload.run;
}

export async function retryWorkflowRun(runId: string): Promise<WorkflowRun> {
  const payload = (await requestJson(
    `${RUNS_BASE}/${encodeURIComponent(runId)}/retry`,
    "POST",
  )) as { run: WorkflowRun };
  return payload.run;
}
