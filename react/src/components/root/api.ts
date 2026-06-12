/**
 * Typed API client for the VLoop backend.
 *
 * All functions are async and resolve to typed response objects.
 * Errors throw with a descriptive message.
 */

import type {
  ChatMessage,
  ClientTelemetryEvent,
  ChatSession,
  DSPyComponent,
  GeneratedView,
  Pipeline,
  Provider,
  RunResult,
} from "./types";

function base(): string {
  const url = (window as any).__HARNESS__?.API_URL ?? "http://localhost:9100";
  return url.replace(/\/api\/.*/, "");
}

export function getAuthToken(): string | null {
  return localStorage.getItem("vloop_auth_token");
}

export function setAuthToken(token: string | null) {
  if (token) {
    localStorage.setItem("vloop_auth_token", token);
  } else {
    localStorage.removeItem("vloop_auth_token");
  }
}

async function request<T>(
  path: string,
  opts: RequestInit = {}
): Promise<T> {
  const token = getAuthToken();
  const headers = {
    "Content-Type": "application/json",
    ...(token ? { "Authorization": `Bearer ${token}` } : {}),
    ...opts.headers,
  };
  const res = await fetch(`${base()}${path}`, {
    headers,
    ...opts,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// ── Chat sessions ──────────────────────────────────────────────────────────

export const listSessions = () =>
  request<ChatSession[]>("/api/chat/sessions");

export const createSession = (title = "New Chat") =>
  request<ChatSession>("/api/chat/sessions", {
    method: "POST",
    body: JSON.stringify({ title }),
  });

export const deleteSession = (id: string) =>
  request<void>(`/api/chat/sessions/${id}`, { method: "DELETE" });

export const renameSession = (id: string, title: string) =>
  request<ChatSession>(`/api/chat/sessions/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });

// ── Chat messages ──────────────────────────────────────────────────────────

export const listMessages = (sessionId: string) =>
  request<ChatMessage[]>(`/api/chat/sessions/${sessionId}/messages`);

export const sendMessage = (sessionId: string, content: string) =>
  request<ChatMessage & { saved_component_id?: string; saved_pipeline_id?: string; saved_view_id?: string }>(
    `/api/chat/sessions/${sessionId}/messages`,
    { method: "POST", body: JSON.stringify({ content }) }
  );

export const getTranscript = (sessionId: string) =>
  request<Record<string, unknown>[]>(`/api/chat/sessions/${sessionId}/transcript`);

// ── DSPy components ────────────────────────────────────────────────────────

export const listComponents = () =>
  request<DSPyComponent[]>("/api/dspy/components");

export const createComponent = (data: {
  name: string;
  description?: string;
  code: string;
  module_type?: string;
}) => request<DSPyComponent>("/api/dspy/components", { method: "POST", body: JSON.stringify(data) });

export const deleteComponent = (id: string) =>
  request<void>(`/api/dspy/components/${id}`, { method: "DELETE" });

export const runComponent = (id: string, inputs: Record<string, string>) =>
  request<RunResult>(`/api/dspy/components/${id}/run`, {
    method: "POST",
    body: JSON.stringify({ inputs }),
  });

// ── Pipelines ──────────────────────────────────────────────────────────────

export const listPipelines = () =>
  request<Pipeline[]>("/api/dspy/pipelines");

export const createPipeline = (data: {
  name: string;
  description?: string;
  steps: Array<{ component_id: string; config?: object }>;
}) => request<Pipeline>("/api/dspy/pipelines", { method: "POST", body: JSON.stringify(data) });

export const updatePipeline = (id: string, data: Partial<Pipeline>) =>
  request<Pipeline>(`/api/dspy/pipelines/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });

export const deletePipeline = (id: string) =>
  request<void>(`/api/dspy/pipelines/${id}`, { method: "DELETE" });

export const runPipeline = (id: string, inputs: Record<string, string>) =>
  request<RunResult>(`/api/dspy/pipelines/${id}/run`, {
    method: "POST",
    body: JSON.stringify({ inputs }),
  });

// ── Providers ──────────────────────────────────────────────────────────────

export const listProviders = () =>
  request<Provider[]>("/api/providers");

export const createProvider = (data: {
  name: string;
  provider_type: string;
  model: string;
  base_url?: string;
  api_key?: string;
}) => request<Provider>("/api/providers", { method: "POST", body: JSON.stringify(data) });

export const updateProvider = (id: string, data: Partial<Provider & { api_key?: string }>) =>
  request<Provider>(`/api/providers/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });

export const deleteProvider = (id: string) =>
  request<void>(`/api/providers/${id}`, { method: "DELETE" });

export const setDefaultProvider = (id: string) =>
  request<Provider>(`/api/providers/${id}/set-default`, { method: "POST" });

export const testProvider = (id: string) =>
  request<{ status: string; response?: string; detail?: string }>(
    `/api/providers/${id}/test`
  );

export const listOllamaModels = (baseUrl?: string) => {
  const url = baseUrl ? `/api/ollama/models?base_url=${encodeURIComponent(baseUrl)}` : "/api/ollama/models";
  return request<{ status: string; models: string[]; detail?: string }>(url);
};

// ── Settings ───────────────────────────────────────────────────────────────

export const getSettings = () =>
  request<Record<string, unknown>>("/api/settings");

export const updateSettings = (settings: Record<string, unknown>) =>
  request<Record<string, unknown>>("/api/settings", {
    method: "PUT",
    body: JSON.stringify({ settings }),
  });

// ── Analytics ──────────────────────────────────────────────────────────────

export const recordTelemetryEvents = (events: ClientTelemetryEvent[]) =>
  request<{ status: "ok"; accepted: number }>("/api/analytics/events", {
    method: "POST",
    body: JSON.stringify({ events }),
  });

// ── Tools ──────────────────────────────────────────────────────────────────

import type {
  ConfirmationRequest,
  FilesystemEntry,
  PolicyConfig,
  ToolCatalogEntry,
  ToolResult,
} from "./types";

export const listTools = () =>
  request<ToolCatalogEntry[]>("/api/tools");

export const getWorkspaceRoot = () =>
  request<{ workspace_root: string }>("/api/tools/workspace");

export const getPolicy = () =>
  request<PolicyConfig>("/api/tools/policy");

export const updatePolicy = (policy: PolicyConfig) =>
  request<PolicyConfig>("/api/tools/policy", {
    method: "PUT",
    body: JSON.stringify(policy),
  });

export const executeTerminal = (
  command: string,
  cwdRelative = ".",
  timeout?: number,
) =>
  request<ToolResult | ConfirmationRequest>("/api/tools/terminal", {
    method: "POST",
    body: JSON.stringify({ command, cwd_relative: cwdRelative, timeout }),
  });

export const listDirectory = (path = ".") =>
  request<ToolResult & { metadata: { entries: FilesystemEntry[] } }>(
    "/api/tools/filesystem/list",
    { method: "POST", body: JSON.stringify({ path }) },
  );

export const readFile = (path: string) =>
  request<ToolResult>("/api/tools/filesystem/read", {
    method: "POST",
    body: JSON.stringify({ path }),
  });

export const statPath = (path: string) =>
  request<ToolResult>("/api/tools/filesystem/stat", {
    method: "POST",
    body: JSON.stringify({ path }),
  });

export const writeFile = (
  path: string,
  content: string,
  createParents = false,
) =>
  request<ToolResult | ConfirmationRequest>("/api/tools/filesystem/write", {
    method: "POST",
    body: JSON.stringify({ path, content, create_parents: createParents }),
  });

export const createPath = (path: string, isDir = false) =>
  request<ToolResult>("/api/tools/filesystem/create", {
    method: "POST",
    body: JSON.stringify({ path, is_dir: isDir }),
  });

export const deletePath = (path: string, recursive = false) =>
  request<ToolResult | ConfirmationRequest>("/api/tools/filesystem/delete", {
    method: "POST",
    body: JSON.stringify({ path, recursive }),
  });

export const movePath = (src: string, dest: string) =>
  request<ToolResult | ConfirmationRequest>("/api/tools/filesystem/move", {
    method: "POST",
    body: JSON.stringify({ src, dest }),
  });

export const confirmAction = (token: string) =>
  request<ToolResult>(`/api/tools/confirm/${token}`, { method: "POST" });

export const cancelConfirmation = (token: string) =>
  request<void>(`/api/tools/confirm/${token}`, { method: "DELETE" });

// ── Generated views ────────────────────────────────────────────────────────

export const generateView = (params: {
  description: string;
  component_name?: string;
  spec?: string;
  session_id?: string;
}) =>
  request<GeneratedView>("/api/views/generate", {
    method: "POST",
    body: JSON.stringify(params),
  });

export const listViews = () =>
  request<GeneratedView[]>("/api/views");

export const deleteView = (id: string) =>
  request<void>(`/api/views/${id}`, { method: "DELETE" });

// ── Agent runs ─────────────────────────────────────────────────────────────

import type { AgentRun, AppManifest, ToolTrace } from "./types";

export const startAgentRun = (data: {
  goal: string;
  session_id?: string;
  autonomy_mode?: string;
  context?: string;
}) =>
  request<AgentRun>("/api/agents/runs", {
    method: "POST",
    body: JSON.stringify(data),
  });

export const listAgentRuns = (limit = 50) =>
  request<AgentRun[]>(`/api/agents/runs?limit=${limit}`);

export const getAgentRun = (id: string) =>
  request<AgentRun>(`/api/agents/runs/${id}`);

export const cancelAgentRun = (id: string) =>
  request<{ run_id: string; status: string }>(`/api/agents/runs/${id}/cancel`, {
    method: "POST",
  });

export const resumeAgentRun = (id: string, confirmedToken?: string) =>
  request<{ run_id: string; status: string }>(`/api/agents/runs/${id}/resume`, {
    method: "POST",
    body: JSON.stringify({ confirmed_token: confirmedToken ?? null }),
  });

export const deleteAgentRun = (id: string) =>
  request<void>(`/api/agents/runs/${id}`, { method: "DELETE" });

// ── App manifests ──────────────────────────────────────────────────────────

export const createAppManifest = (data: {
  name: string;
  description?: string;
  backend_type?: string;
  backend_id?: string;
  react_views?: string[];
  permissions?: string[];
  state_schema?: Record<string, unknown>;
  agent_run_id?: string;
}) =>
  request<AppManifest>("/api/apps/manifests", {
    method: "POST",
    body: JSON.stringify(data),
  });

export const listAppManifests = (status?: string) => {
  const q = status ? `?status=${encodeURIComponent(status)}` : "";
  return request<AppManifest[]>(`/api/apps/manifests${q}`);
};

export const getAppManifest = (id: string) =>
  request<AppManifest>(`/api/apps/manifests/${id}`);

export const updateAppManifest = (id: string, data: Partial<AppManifest>) =>
  request<AppManifest>(`/api/apps/manifests/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });

export const promoteAppManifest = (id: string, status: string) =>
  request<AppManifest>(`/api/apps/manifests/${id}/promote`, {
    method: "POST",
    body: JSON.stringify({ status }),
  });

export const deleteAppManifest = (id: string) =>
  request<void>(`/api/apps/manifests/${id}`, { method: "DELETE" });

// ── Tool traces ────────────────────────────────────────────────────────────

export const listToolTraces = (params?: {
  tool_name?: string;
  session_id?: string;
  run_step_id?: string;
  limit?: number;
}) => {
  const qs = new URLSearchParams();
  if (params?.tool_name) qs.set("tool_name", params.tool_name);
  if (params?.session_id) qs.set("session_id", params.session_id);
  if (params?.run_step_id) qs.set("run_step_id", params.run_step_id);
  if (params?.limit) qs.set("limit", String(params.limit));
  const q = qs.toString() ? `?${qs.toString()}` : "";
  return request<ToolTrace[]>(`/api/apps/traces${q}`);
};

// ── Browser tool ───────────────────────────────────────────────────────────

export const executeBrowser = (params: {
  operation: string;
  url?: string;
  selector?: string;
  value?: string;
  expression?: string;
  full_page?: boolean;
}) =>
  request<ToolResult>("/api/tools/browser", {
    method: "POST",
    body: JSON.stringify(params),
  });

// ── Component versions (eval/rollback) ────────────────────────────────────────

export interface ComponentVersion {
  id: string;
  component_id: string;
  version_number: number;
  name: string;
  description: string;
  code: string;
  module_type: string;
  change_summary: string;
  created_at: string;
}

export interface EvalDataset {
  id: string;
  component_id: string;
  name: string;
  description: string;
  examples: Array<{ inputs: Record<string, unknown>; expected_outputs: Record<string, unknown> }>;
  created_at: string;
  updated_at: string;
}

export interface EvalResult {
  component_id: string;
  dataset_id: string;
  total: number;
  passed: number;
  failed: number;
  results: Array<{
    index: number;
    passed: boolean;
    inputs: Record<string, unknown>;
    expected_outputs: Record<string, unknown>;
    actual_outputs: Record<string, unknown>;
    error?: string;
  }>;
}

export const listComponentVersions = (componentId: string) =>
  request<ComponentVersion[]>(`/api/dspy/components/${componentId}/versions`);

export const snapshotComponent = (componentId: string, changeSummary = "") =>
  request<ComponentVersion>(`/api/dspy/components/${componentId}/snapshot`, {
    method: "POST",
    body: JSON.stringify({ change_summary: changeSummary }),
  });

export const rollbackComponent = (componentId: string, versionId: string) =>
  request<{ component_id: string; rolled_back_to: number; snapshot_id: string }>(
    `/api/dspy/components/${componentId}/rollback`,
    { method: "POST", body: JSON.stringify({ version_id: versionId }) },
  );

export const listEvalDatasets = (componentId: string) =>
  request<EvalDataset[]>(`/api/dspy/components/${componentId}/eval-datasets`);

export const createEvalDataset = (
  componentId: string,
  data: { name: string; description?: string; examples?: unknown[] },
) =>
  request<EvalDataset>(`/api/dspy/components/${componentId}/eval-datasets`, {
    method: "POST",
    body: JSON.stringify(data),
  });

export const updateEvalDataset = (
  componentId: string,
  datasetId: string,
  data: Partial<{ name: string; description: string; examples: unknown[] }>,
) =>
  request<EvalDataset>(`/api/dspy/components/${componentId}/eval-datasets/${datasetId}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });

export const deleteEvalDataset = (componentId: string, datasetId: string) =>
  request<void>(`/api/dspy/components/${componentId}/eval-datasets/${datasetId}`, {
    method: "DELETE",
  });

export const evaluateComponent = (componentId: string, datasetId?: string) =>
  request<EvalResult>(`/api/dspy/components/${componentId}/evaluate`, {
    method: "POST",
    body: JSON.stringify({ dataset_id: datasetId }),
  });

// ── Database tool ──────────────────────────────────────────────────────────

export const executeDatabase = (params: {
  operation: "schema_info" | "query_read" | "query_write";
  sql?: string;
  params?: Record<string, unknown>;
}) =>
  request<ToolResult | ConfirmationRequest>("/api/tools/database", {
    method: "POST",
    body: JSON.stringify(params),
  });

// ── Browser tool ──────────────────────────────────────────────────────────

export const executeBrowserTool = (params: {
  operation: string;
  url?: string;
  selector?: string;
  value?: string;
  expression?: string;
  full_page?: boolean;
}) =>
  request<ToolResult | ConfirmationRequest>("/api/tools/browser", {
    method: "POST",
    body: JSON.stringify(params),
  });

// ── Rollback ───────────────────────────────────────────────────────────────

export const listRollbacks = (params: { path: string; backup_index?: number }) =>
  request<any[]>("/api/tools/rollback/list", {
    method: "POST",
    body: JSON.stringify(params),
  });

export const executeRollback = (params: { path: string; backup_index?: number }) =>
  request<{ success: boolean; message: string }>("/api/tools/rollback/execute", {
    method: "POST",
    body: JSON.stringify(params),
  });

export const cleanupRollbacks = () =>
  request<{ removed_count: number; total_size_bytes: number; total_size_mb: number }>(
    "/api/tools/rollback/cleanup",
    { method: "POST" }
  );

// ── Component marketplace ───────────────────────────────────────────────────

export interface MarketplaceComponent {
  id: string;
  name: string;
  description: string;
  category: string;
  tags: string[];
  version: string;
  author: string;
  created_at: string;
}

export const listMarketplaceComponents = () =>
  request<MarketplaceComponent[]>("/api/dspy/components");

export const activateComponent = (componentId: string) =>
  request<{ component_id: string; status: string }>(`/api/dspy/components/${componentId}/activate`, {
    method: "POST",
  });

export const cloneComponent = (componentId: string, newName: string) =>
  request<{ component_id: string; cloned_from: string }>(`/api/dspy/components/${componentId}/clone`, {
    method: "POST",
    body: JSON.stringify({ name: newName }),
  });

// ── Metrics ─────────────────────────────────────────────────────────────────

export interface MetricsData {
  counters: Array<{ name: string; value: number; tags: Record<string, string> }>;
  gauges: Array<{ name: string; value: number; tags: Record<string, string> }>;
  histograms: Array<{ name: string; summary: Record<string, number>; tags: Record<string, string> }>;
}

export interface MetricsSummary {
  total_counters: number;
  total_gauges: number;
  total_histograms: number;
  key_metrics: Record<string, number | Record<string, number>>;
}

export const getMetrics = () =>
  request<MetricsData>("/api/metrics");

export const getMetricsSummary = () =>
  request<MetricsSummary>("/api/metrics/summary");

export const resetMetrics = () =>
  request<{ status: string }>("/api/metrics/reset", { method: "POST" });


// ── Auth & User Management ──────────────────────────────────────────────────

export const login = (data: Record<string, string>) =>
  request<{ access_token: string; token_type: string }>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify(data),
  });

export const register = (data: Record<string, string>) =>
  request<any>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify(data),
  });

export const getMe = () =>
  request<any>("/api/auth/me");


// ── Chat Channels ─────────────────────────────────────────────────────────────

export interface ChannelType {
  id: string;
  name: string;
  description: string;
  is_private: boolean;
  created_by: string;
  created_at: string;
}

export interface ChannelMessageType {
  id: string;
  channel_id: string;
  sender_id: string;
  sender_name: string;
  sender_type: string;
  content: string;
  created_at: string;
}

export const listChannels = () =>
  request<ChannelType[]>("/api/channels");

export const createChannel = (data: { name: string; description?: string; is_private?: boolean }) =>
  request<ChannelType>("/api/channels", {
    method: "POST",
    body: JSON.stringify(data),
  });

export const joinChannel = (channelId: string) =>
  request<{ id: string; channel_id: string; user_id: string; role: string }>(
    `/api/channels/${channelId}/join`,
    { method: "POST" }
  );

export const listChannelMessages = (channelId: string, limit = 100) =>
  request<ChannelMessageType[]>(`/api/channels/${channelId}/messages?limit=${limit}`);

export const sendChannelMessage = (channelId: string, content: string) =>
  request<ChannelMessageType>(`/api/channels/${channelId}/messages`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });

