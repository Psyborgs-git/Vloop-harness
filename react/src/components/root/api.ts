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
  request<ChatMessage & { saved_component_id?: string; saved_pipeline_id?: string }>(
    `/api/chat/sessions/${sessionId}/messages`,
    { method: "POST", body: JSON.stringify({ content }) }
  );

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
