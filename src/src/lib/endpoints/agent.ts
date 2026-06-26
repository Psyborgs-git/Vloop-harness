import type {
  AgentConfig,
  AgentMutationPayload,
  AgentTemplate,
  AgentValidationResult,
  InvocationRecord,
  InvokeAgentRequest,
  ChatMessage,
  InvocationEvent,
} from "../types";
import { requestJson, requestWithFallback, unwrapEntity } from "../api-client";
import {
  normalizeAgent,
  normalizeAgentList,
  normalizeTemplateList,
  normalizeInvocation,
  normalizeInvocationList,
  normalizeInvocationEventList,
} from "../normalizers";

export async function listAgentTemplates(): Promise<AgentTemplate[]> {
  const payload = await requestWithFallback<unknown>([
    { path: "/api/v1/agents/templates" },
  ]);
  return normalizeTemplateList(payload);
}

export async function validateAgent(
  payload: AgentMutationPayload,
  agentId?: string,
): Promise<AgentValidationResult> {
  const response = await requestWithFallback<unknown>(
    agentId
      ? [
          {
            path: `/api/v1/agents/${encodeURIComponent(agentId)}/validate`,
            method: "POST",
            body: payload,
          },
          {
            path: "/api/v1/agents/validate",
            method: "POST",
            body: payload,
          },
        ]
      : [
          {
            path: "/api/v1/agents/validate",
            method: "POST",
            body: payload,
          },
        ],
  );

  const record = asRecord(response);
  const normalized = record.normalized
    ? normalizeAgent(record.normalized)
    : normalizeAgent(unwrapEntity(response, ["agent", "data", "item"]));

  function readBoolean(rec: Record<string, unknown>, ...keys: string[]): boolean | null {
    for (const key of keys) {
      const v = rec[key];
      if (typeof v === "boolean") return v;
      if (typeof v === "number") return v !== 0;
      if (typeof v === "string") {
        const n = v.trim().toLowerCase();
        if (["true", "1", "yes", "on"].includes(n)) return true;
        if (["false", "0", "no", "off"].includes(n)) return false;
      }
    }
    return null;
  }

  return {
    valid: readBoolean(record, "valid") ?? true,
    normalized: normalized.id ? normalized : null,
  };
}

export async function saveAgent(
  payload: AgentMutationPayload,
  agentId?: string,
): Promise<AgentConfig> {
  const response = await requestWithFallback<unknown>(
    agentId
      ? [
          {
            path: `/api/v1/agents/${encodeURIComponent(agentId)}`,
            method: "PUT",
            body: payload,
          },
          {
            path: `/api/v1/agents/${encodeURIComponent(agentId)}`,
            method: "POST",
            body: payload,
          },
        ]
      : [{ path: "/api/v1/agents", method: "POST", body: payload }],
  );

  return normalizeAgent(unwrapEntity(response, ["agent", "data", "item"]));
}

export async function deleteAgent(agentId: string): Promise<void> {
  await requestWithFallback<unknown>([
    { path: `/api/v1/agents/${encodeURIComponent(agentId)}`, method: "DELETE" },
  ]);
}

export async function listInvocations(
  agentId?: string,
): Promise<InvocationRecord[]> {
  const query = new URLSearchParams();
  if (agentId) {
    query.set("agentId", agentId);
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";

  const payload = await requestWithFallback<unknown>([
    { path: `/api/v1/invocations${suffix}` },
    {
      path: agentId
        ? `/api/v1/agents/${encodeURIComponent(agentId)}/invocations`
        : "/api/v1/invocations",
    },
  ]);

  return normalizeInvocationList(payload);
}

export async function getInvocation(
  invocationId: string,
): Promise<InvocationRecord> {
  const response = await requestWithFallback<unknown>([
    { path: `/api/v1/invocations/${encodeURIComponent(invocationId)}` },
  ]);
  return normalizeInvocation(
    unwrapEntity(response, ["invocation", "data", "item"]),
  );
}

export async function getInvocationEvents(
  invocationId: string,
): Promise<InvocationEvent[]> {
  const payload = await requestWithFallback<unknown>([
    { path: `/api/v1/invocations/${encodeURIComponent(invocationId)}/events` },
    {
      path: `/api/v1/invocation-events?invocationId=${encodeURIComponent(invocationId)}`,
    },
  ]);
  return normalizeInvocationEventList(payload);
}

export async function invokeAgent(
  agentId: string,
  request: InvokeAgentRequest,
): Promise<InvocationRecord> {
  const body = {
    inputs: request.inputs,
    overrides: request.overrides ?? {},
  };

  const response = await requestWithFallback<unknown>([
    {
      path: `/api/v1/agents/${encodeURIComponent(agentId)}/invoke`,
      method: "POST",
      body,
    },
    {
      path: `/api/v1/agents/${encodeURIComponent(agentId)}/invocations`,
      method: "POST",
      body,
    },
    {
      path: "/api/v1/invocations",
      method: "POST",
      body: { agentId, ...body },
    },
  ]);

  return normalizeInvocation(
    unwrapEntity(response, ["invocation", "data", "item"]),
  );
}

export async function chatWithAgent(
  agentId: string,
  messages: ChatMessage[],
  overrides?: {
    providerId?: string;
    model?: string;
    temperature?: number;
    maxTokens?: number;
  },
): Promise<{ message: ChatMessage; invocation: InvocationRecord }> {
  const conversationText = messages
    .filter((m) => m.role !== "system")
    .map((m) => `${m.role === "user" ? "User" : "Assistant"}: ${m.content}`)
    .join("\n");

  const systemMessage = messages.find((m) => m.role === "system");
  const requestText = systemMessage
    ? `${systemMessage.content}\n\nConversation:\n${conversationText}`
    : conversationText;

  const invocation = await invokeAgent(agentId, {
    inputs: { request_text: requestText },
    overrides: overrides ?? {},
  });

  const responseContent =
    invocation.outputText ??
    (invocation.outputJson
      ? JSON.stringify(invocation.outputJson, null, 2)
      : (invocation.errorMessage ?? "No response content."));

  const message: ChatMessage = {
    role: "assistant",
    content: responseContent,
    timestamp: invocation.finishedAt ?? invocation.createdAt ?? undefined,
  };

  return { message, invocation };
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

export async function listAgentsInternal(): Promise<AgentConfig[]> {
  const payload = await requestWithFallback<unknown>([
    { path: "/api/v1/agents" },
  ]);
  return normalizeAgentList(payload);
}

export async function listInvocationsInternal(): Promise<InvocationRecord[]> {
  const payload = await requestWithFallback<unknown>([
    { path: "/api/v1/invocations" },
  ]);
  return normalizeInvocationList(payload);
}

export async function listAgentTemplatesInternal(): Promise<AgentTemplate[]> {
  const payload = await requestWithFallback<unknown>([
    { path: "/api/v1/agents/templates" },
  ]);
  return normalizeTemplateList(payload);
}
