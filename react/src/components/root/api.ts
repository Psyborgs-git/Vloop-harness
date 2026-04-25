/**
 * Typed API client for the VLoop backend.
 *
 * All functions are async and resolve to typed response objects.
 * Errors throw with a descriptive message.
 */

import type {
  ChatMessage,
  ChatSession,
  DSPyComponent,
  GeneratedView,
  Pipeline,
  Provider,
  RunResult,
} from "./types";

function base(): string {
  const url = (window as any).__HARNESS__?.API_URL ?? "http://localhost:8000";
  return url.replace(/\/api\/.*/, "");
}

async function request<T>(
  path: string,
  opts: RequestInit = {}
): Promise<T> {
  const res = await fetch(`${base()}${path}`, {
    headers: { "Content-Type": "application/json", ...opts.headers },
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
