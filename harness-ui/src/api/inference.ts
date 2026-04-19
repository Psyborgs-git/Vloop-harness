const BASE_URL = "http://localhost:47201";

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`API error ${res.status}: ${err}`);
  }
  return res.json() as Promise<T>;
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`);
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json() as Promise<T>;
}

export interface AgentRunResponse {
  run_id: string;
  answer: string;
  loop: string;
  steps?: unknown[];
  [k: string]: unknown;
}

export const agentRun = (agent: string, task: string, config?: Record<string, unknown>) =>
  post<AgentRunResponse>("/agent/run", { agent, task, config });

export const listAgentLoops = () => get<string[]>("/agent/loops");

export const listModules = () => get<{ modules: string[] }>("/module/list");

export const createModule = (name: string, code: string) =>
  post<{ status: string; sha: string }>("/module/create", { name, code });

export const rollbackModule = (name: string, version: string) =>
  post<{ status: string }>("/module/rollback", { name, version });

export const listPipelines = () => get<{ pipelines: string[] }>("/pipeline/list");

export const runPipeline = (name: string, inputs: Record<string, unknown>) =>
  post<{ result: unknown }>("/pipeline/run", { name, inputs });

export const health = () => get<{ status: string; uptime_s: number }>("/health");

export function createStreamWebSocket(
  onMessage: (msg: unknown) => void
): WebSocket {
  const ws = new WebSocket(`ws://localhost:47201/stream`);
  ws.onmessage = (e) => {
    try {
      onMessage(JSON.parse(e.data));
    } catch {
      onMessage(e.data);
    }
  };
  return ws;
}
