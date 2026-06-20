export type ProviderTypeKey =
  | "mock"
  | "ollama"
  | "openai"
  | "anthropic"
  | "openrouter"
  | "azure"
  | string;

export type SecretMode = "none" | "env" | "session" | string;
export type ReasoningMode = "predict" | "chain_of_thought" | string;
export type OutputMode = "text" | "json" | string;

export interface ProviderTypeSpec {
  key: ProviderTypeKey;
  label: string;
  description: string;
  secretModes: SecretMode[];
  defaultModel: string;
  modelExamples: string[];
  apiBaseHint: string | null;
  apiVersionHint: string | null;
  requiresSecret: boolean;
  localOnlyHttp: boolean;
}

export interface ProviderConfig {
  id: string;
  name: string;
  providerType: ProviderTypeKey;
  enabled: boolean;
  defaultModel: string;
  apiBase: string | null;
  apiVersion: string | null;
  organization: string | null;
  secretMode: SecretMode;
  secretEnvVar: string | null;
  hasSecret: boolean;
  revision: number;
  lastTestStatus: string;
  lastTestError: string | null;
  lastTestedAt: string | null;
  createdAt: string | null;
  updatedAt: string | null;
}

export interface AgentInputField {
  name: string;
  label: string;
  description: string | null;
  required: boolean;
}

export interface AgentConfig {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  enabled: boolean;
  instructions: string;
  reasoningMode: ReasoningMode;
  inputFields: AgentInputField[];
  outputMode: OutputMode;
  outputFieldName: string;
  outputSchema: Record<string, unknown> | null;
  defaultProviderId: string;
  modelOverride: string | null;
  temperature: number;
  maxTokens: number;
  revision: number;
  createdAt: string | null;
  updatedAt: string | null;
}

export interface AgentTemplate {
  id: string;
  name: string;
  description: string;
  instructions: string;
  inputFields: AgentInputField[];
  outputMode: OutputMode;
  outputFieldName: string;
  outputSchema: Record<string, unknown> | null;
  reasoningMode: ReasoningMode;
  temperature: number;
  maxTokens: number;
}

export interface InvocationRecord {
  id: string;
  agentId: string;
  agentRevision: number;
  providerId: string;
  providerRevision: number;
  status: string;
  inputs: Record<string, unknown>;
  overrides: Record<string, unknown>;
  resolvedModel: string | null;
  resolvedConfig: Record<string, unknown>;
  outputText: string | null;
  outputJson: Record<string, unknown> | null;
  reasoningText: string | null;
  usage: Record<string, unknown> | null;
  errorCode: string | null;
  errorMessage: string | null;
  createdAt: string | null;
  startedAt: string | null;
  finishedAt: string | null;
}

export interface InvocationEvent {
  seq: number;
  type: string;
  message: string;
  payload: Record<string, unknown>;
  createdAt: string | null;
}

export interface WindowSnapshot {
  backend: string | null;
  isOpen: boolean;
  openRequests: number;
  lastOpenReason: string | null;
  lastOpenedAtUnixMs: number | null;
  lastFocusedAtUnixMs: number | null;
  shellUrl: string | null;
  loadedUrl: string | null;
  lastLoadedAtUnixMs: number | null;
}

export interface HealthSnapshot {
  status: string | null;
  version: string | null;
  kernelEndpoint: string | null;
  httpBaseUrl: string | null;
  shellUrl: string | null;
  sessionId: string | null;
  lastError: string | null;
  window: WindowSnapshot | null;
}

export interface DependencyStatus {
  name: string;
  state: string;
  message: string;
  detectedVersion: string | null;
  remediation: string | null;
}

export interface DependencySnapshot {
  dependencies: DependencyStatus[];
  error?: string;
}

export interface KernelActiveConfig {
  ipcEndpoint: string | null;
  bootId: string | null;
  runtimeRoot: string | null;
  availableRuntimes: string[];
  features: Record<string, string>;
}

export interface SessionSnapshot {
  status: string | null;
  kernelEndpoint: string | null;
  httpBaseUrl: string | null;
  shellUrl: string | null;
  sessionId: string | null;
  grantedScopes: string[];
  lastRegisteredAtUnixMs: number | null;
  lastHeartbeatAtUnixMs: number | null;
  lastError: string | null;
  activeConfig: KernelActiveConfig | null;
}

export interface KernelEventRecord {
  eventId: string;
  eventType: string;
  resourceType: string;
  resourceId: string;
  status: string;
  message: string;
  timestampUnixMs: number;
  attributes: Record<string, string>;
}

export interface SystemSnapshot {
  health: HealthSnapshot;
  session: SessionSnapshot;
  window: WindowSnapshot;
  dependencies: DependencySnapshot;
  recentEvents: KernelEventRecord[];
  eventCount: number;
}

export interface BootstrapPayload {
  providers: ProviderConfig[];
  agents: AgentConfig[];
  invocations: InvocationRecord[];
  providerCatalog: ProviderTypeSpec[];
  agentTemplates: AgentTemplate[];
  apiAvailable: boolean;
  source: "bootstrap" | "assembled" | "fallback";
  warning: string | null;
}

export interface ProviderMutationPayload {
  name: string;
  providerType: ProviderTypeKey;
  enabled: boolean;
  defaultModel: string;
  apiBase?: string | null;
  apiVersion?: string | null;
  organization?: string | null;
  secretMode: SecretMode;
  secretEnvVar?: string | null;
  sessionSecret?: string;
  clearSessionSecret?: boolean;
}

export interface ProviderTestResult {
  provider: ProviderConfig;
  status: string;
  preview: string | null;
  error: string | null;
  testedAt: string | null;
}

export interface AgentMutationPayload {
  name: string;
  slug: string;
  description?: string | null;
  instructions: string;
  reasoningMode: ReasoningMode;
  inputFields: AgentInputField[];
  outputMode: OutputMode;
  outputFieldName: string;
  outputSchema?: Record<string, unknown> | null;
  defaultProviderId: string;
  modelOverride?: string | null;
  temperature: number;
  maxTokens: number;
  enabled: boolean;
}

export interface AgentValidationResult {
  valid: boolean;
  normalized: AgentConfig | null;
}

export interface InvokeAgentRequest {
  inputs: Record<string, unknown>;
  overrides?: {
    providerId?: string;
    model?: string;
    temperature?: number;
    maxTokens?: number;
  };
}

interface RequestCandidate {
  path: string;
  method?: string;
  body?: unknown;
}

// -- Workload types ----------------------------------------------------------

export interface WorkloadSpec {
  image: string;
  command: string[];
  ports: number[];
  environment: Record<string, string>;
}

export interface WorkloadRecord {
  workloadId: string;
  class: string;
  state: string;
  spec: WorkloadSpec;
  createdAtUnixMs: number;
  updatedAtUnixMs: number;
  exitCode: number | null;
  terminationReason: string;
  exposedPorts: number[];
  previewUrl: string;
}

export interface WorkloadLogLine {
  stream: string;
  line: string;
  timestampUnixMs: number;
}

export interface WorkloadLogsResponse {
  workloadId: string;
  logs: WorkloadLogLine[];
}

const FALLBACK_STATUSES = new Set([404, 405]);

export const DEFAULT_PROVIDER_CATALOG: ProviderTypeSpec[] = [
  {
    key: "mock",
    label: "VLoop Mock LM",
    description:
      "Local deterministic DSPy-compatible provider for smoke testing and first-run exploration.",
    secretModes: ["none"],
    defaultModel: "mock/echo-agent",
    modelExamples: ["mock/echo-agent"],
    apiBaseHint: null,
    apiVersionHint: null,
    requiresSecret: false,
    localOnlyHttp: false,
  },
  {
    key: "ollama",
    label: "Ollama",
    description:
      "Use a local Ollama daemon over loopback without any cloud credentials.",
    secretModes: ["none"],
    defaultModel: "ollama/llama3.2",
    modelExamples: ["ollama/llama3.2", "ollama/qwen2.5:7b"],
    apiBaseHint: "http://127.0.0.1:11434",
    apiVersionHint: null,
    requiresSecret: false,
    localOnlyHttp: true,
  },
  {
    key: "openai",
    label: "OpenAI",
    description: "Use OpenAI-hosted chat or responses models through LiteLLM.",
    secretModes: ["env", "session"],
    defaultModel: "openai/gpt-4o-mini",
    modelExamples: ["openai/gpt-4o-mini", "openai/gpt-4.1-mini"],
    apiBaseHint: null,
    apiVersionHint: null,
    requiresSecret: true,
    localOnlyHttp: false,
  },
  {
    key: "anthropic",
    label: "Anthropic",
    description: "Use Anthropic Claude models through LiteLLM.",
    secretModes: ["env", "session"],
    defaultModel: "anthropic/claude-3-5-sonnet-latest",
    modelExamples: [
      "anthropic/claude-3-5-sonnet-latest",
      "anthropic/claude-3-5-haiku-latest",
    ],
    apiBaseHint: null,
    apiVersionHint: null,
    requiresSecret: true,
    localOnlyHttp: false,
  },
  {
    key: "openrouter",
    label: "OpenRouter",
    description:
      "Route OpenAI-compatible traffic through OpenRouter with a provider-prefixed model string.",
    secretModes: ["env", "session"],
    defaultModel: "openrouter/openai/gpt-4o-mini",
    modelExamples: [
      "openrouter/openai/gpt-4o-mini",
      "openrouter/anthropic/claude-3.5-sonnet",
    ],
    apiBaseHint: "https://openrouter.ai/api/v1",
    apiVersionHint: null,
    requiresSecret: true,
    localOnlyHttp: false,
  },
  {
    key: "azure",
    label: "Azure OpenAI",
    description:
      "Use Azure OpenAI deployments via LiteLLM with an Azure-style deployment model string.",
    secretModes: ["env", "session"],
    defaultModel: "azure/my-deployment",
    modelExamples: ["azure/my-deployment"],
    apiBaseHint: "https://your-resource.openai.azure.com",
    apiVersionHint: "2024-10-21",
    requiresSecret: true,
    localOnlyHttp: false,
  },
];

export class ApiError extends Error {
  readonly status: number | null;
  readonly body: unknown;

  constructor(
    message: string,
    status: number | null = null,
    body: unknown = null,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

export async function getBootstrap(): Promise<BootstrapPayload> {
  try {
    const payload = await requestWithFallback<unknown>([
      { path: "/api/v1/bootstrap" },
      { path: "/api/v1" },
      { path: "/api/v1/state" },
    ]);

    let bootstrap = normalizeBootstrapPayload(payload, "bootstrap");
    if (bootstrap.agentTemplates.length === 0) {
      try {
        bootstrap = {
          ...bootstrap,
          agentTemplates: await listAgentTemplates(),
        };
      } catch {
        // Best-effort only.
      }
    }
    return bootstrap;
  } catch (error) {
    if (
      error instanceof ApiError &&
      FALLBACK_STATUSES.has(error.status ?? -1)
    ) {
      return assembleBootstrapFromIndividualEndpoints();
    }
    throw error;
  }
}

export async function getSystemSnapshot(): Promise<SystemSnapshot> {
  const [
    healthPayload,
    sessionPayload,
    windowPayload,
    eventsPayload,
    depsPayload,
  ] = await Promise.all([
    requestJson<unknown>("/health"),
    requestJson<unknown>("/session"),
    requestJson<unknown>("/window"),
    requestJson<unknown>("/events/recent"),
    requestJson<unknown>("/dependencies"),
  ]);

  const eventsRecord = asRecord(eventsPayload);
  const recentEventsSource = Array.isArray(eventsPayload)
    ? eventsPayload
    : Array.isArray(eventsRecord.recentEvents)
      ? eventsRecord.recentEvents
      : Array.isArray(eventsRecord.recent_events)
        ? eventsRecord.recent_events
        : [];

  const recentEvents = sortKernelEvents(
    recentEventsSource.map((event: unknown) => normalizeKernelEvent(event)),
  );

  return {
    health: normalizeHealthSnapshot(healthPayload),
    session: normalizeSessionSnapshot(sessionPayload),
    window: normalizeWindowSnapshot(windowPayload),
    dependencies: normalizeDependencySnapshot(depsPayload),
    recentEvents,
    eventCount:
      readNumber(eventsRecord, "eventCount", "event_count") ??
      recentEvents.length,
  };
}

export async function saveProvider(
  payload: ProviderMutationPayload,
  providerId?: string,
): Promise<ProviderConfig> {
  const response = await requestWithFallback<unknown>(
    providerId
      ? [
          {
            path: `/api/v1/providers/${encodeURIComponent(providerId)}`,
            method: "PUT",
            body: payload,
          },
          {
            path: `/api/v1/providers/${encodeURIComponent(providerId)}`,
            method: "POST",
            body: payload,
          },
        ]
      : [{ path: "/api/v1/providers", method: "POST", body: payload }],
  );

  return normalizeProvider(
    unwrapEntity(response, ["provider", "data", "item"]),
  );
}

export async function testProvider(
  providerId: string,
): Promise<ProviderTestResult> {
  const response = await requestWithFallback<unknown>([
    {
      path: `/api/v1/providers/${encodeURIComponent(providerId)}/test`,
      method: "POST",
    },
    {
      path: "/api/v1/providers/test",
      method: "POST",
      body: { providerId },
    },
  ]);

  const record = asRecord(response);
  return {
    provider: normalizeProvider(
      unwrapEntity(response, ["provider", "data", "item"]),
    ),
    status: readString(record, "status") ?? "unknown",
    preview: readString(record, "preview"),
    error: readString(record, "error", "message"),
    testedAt: readString(record, "testedAt", "tested_at"),
  };
}

export async function deleteProvider(providerId: string): Promise<void> {
  await requestWithFallback<unknown>([
    {
      path: `/api/v1/providers/${encodeURIComponent(providerId)}`,
      method: "DELETE",
    },
  ]);
}

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

export function sortProviders(providers: ProviderConfig[]): ProviderConfig[] {
  return [...providers].sort((left, right) => {
    const delta =
      toSortableTimestamp(right.updatedAt) -
      toSortableTimestamp(left.updatedAt);
    if (delta !== 0) {
      return delta;
    }
    return left.name.localeCompare(right.name);
  });
}

export function sortAgents(agents: AgentConfig[]): AgentConfig[] {
  return [...agents].sort((left, right) => {
    const delta =
      toSortableTimestamp(right.updatedAt) -
      toSortableTimestamp(left.updatedAt);
    if (delta !== 0) {
      return delta;
    }
    return left.name.localeCompare(right.name);
  });
}

export function sortInvocations(
  invocations: InvocationRecord[],
): InvocationRecord[] {
  return [...invocations].sort((left, right) => {
    const delta =
      toSortableTimestamp(right.createdAt) -
      toSortableTimestamp(left.createdAt);
    if (delta !== 0) {
      return delta;
    }
    return right.id.localeCompare(left.id);
  });
}

export function sortKernelEvents(
  events: KernelEventRecord[],
): KernelEventRecord[] {
  return [...events].sort(
    (left, right) => right.timestampUnixMs - left.timestampUnixMs,
  );
}

export function isTerminalInvocationStatus(
  status: string | null | undefined,
): boolean {
  return (
    status === "succeeded" || status === "failed" || status === "cancelled"
  );
}

export function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

// -- Workload API -------------------------------------------------------------

export async function listWorkloads(): Promise<WorkloadRecord[]> {
  const payload = (await requestJson("/api/v1/workloads", "GET")) as {
    workloads: unknown;
  };
  return normalizeStringArray(payload.workloads).map(normalizeWorkloadRecord);
}

export async function createWorkload(spec: {
  image: string;
  command?: string[];
  ports?: number[];
  environment?: Record<string, string>;
  class?: string;
}): Promise<WorkloadRecord> {
  const payload = (await requestJson("/api/v1/workloads", "POST", {
    image: spec.image,
    command: spec.command ?? [],
    ports: spec.ports ?? [],
    environment: spec.environment ?? {},
    class: spec.class ?? "HARNESS",
  })) as { workload: unknown };
  return normalizeWorkloadRecord(payload.workload);
}

export async function startWorkload(
  workloadId: string,
): Promise<WorkloadRecord> {
  const payload = (await requestJson(
    `/api/v1/workloads/${encodeURIComponent(workloadId)}/start`,
    "POST",
  )) as { workload: unknown };
  return normalizeWorkloadRecord(payload.workload);
}

export async function stopWorkload(
  workloadId: string,
): Promise<WorkloadRecord> {
  const payload = (await requestJson(
    `/api/v1/workloads/${encodeURIComponent(workloadId)}/stop`,
    "POST",
  )) as { workload: unknown };
  return normalizeWorkloadRecord(payload.workload);
}

export async function getWorkloadLogs(
  workloadId: string,
): Promise<WorkloadLogsResponse> {
  const payload = (await requestJson(
    `/api/v1/workloads/${encodeURIComponent(workloadId)}/logs`,
    "GET",
  )) as WorkloadLogsResponse;
  return payload;
}

function normalizeWorkloadRecord(input: unknown): WorkloadRecord {
  const record = asRecord(input);
  const rawSpec = asRecord(record.spec);
  return {
    workloadId: readString(record.workloadId, ""),
    class: readString(record.class, "unspecified"),
    state: readString(record.state, "unspecified"),
    spec: {
      image: readString(rawSpec.image, ""),
      command: normalizeStringArray(rawSpec.command),
      ports: normalizeStringArray(rawSpec.ports).map(Number),
      environment: asRecord(rawSpec.environment) as Record<string, string>,
    },
    createdAtUnixMs: readNumber(record.createdAtUnixMs, 0),
    updatedAtUnixMs: readNumber(record.updatedAtUnixMs, 0),
    exitCode: record.exitCode != null ? readNumber(record.exitCode, 0) : null,
    terminationReason: readString(record.terminationReason, ""),
    exposedPorts: normalizeStringArray(record.exposedPorts).map(Number),
    previewUrl: readString(record.previewUrl, ""),
  };
}

async function assembleBootstrapFromIndividualEndpoints(): Promise<BootstrapPayload> {
  const [
    providersResult,
    agentsResult,
    invocationsResult,
    catalogResult,
    templatesResult,
  ] = await Promise.allSettled([
    listProvidersInternal(),
    listAgentsInternal(),
    listInvocationsInternal(),
    listProviderCatalogInternal(),
    listAgentTemplatesInternal(),
  ]);

  const providers =
    providersResult.status === "fulfilled" ? providersResult.value : [];
  const agents = agentsResult.status === "fulfilled" ? agentsResult.value : [];
  const invocations =
    invocationsResult.status === "fulfilled" ? invocationsResult.value : [];
  const providerCatalog =
    catalogResult.status === "fulfilled" && catalogResult.value.length > 0
      ? catalogResult.value
      : DEFAULT_PROVIDER_CATALOG;
  const agentTemplates =
    templatesResult.status === "fulfilled" ? templatesResult.value : [];

  const apiAvailable = [
    providersResult,
    agentsResult,
    invocationsResult,
    catalogResult,
    templatesResult,
  ].some((result) => result.status === "fulfilled");

  return {
    providers,
    agents,
    invocations,
    providerCatalog,
    agentTemplates,
    apiAvailable,
    source: apiAvailable ? "assembled" : "fallback",
    warning: apiAvailable
      ? null
      : "This Control Plane build does not expose the /api/v1 configuration endpoints yet. System status is available, but provider, agent, and playground actions will remain read-only until those routes are added.",
  };
}

async function listProvidersInternal(): Promise<ProviderConfig[]> {
  const payload = await requestWithFallback<unknown>([
    { path: "/api/v1/providers" },
  ]);
  return normalizeProviderList(payload);
}

async function listAgentsInternal(): Promise<AgentConfig[]> {
  const payload = await requestWithFallback<unknown>([
    { path: "/api/v1/agents" },
  ]);
  return normalizeAgentList(payload);
}

async function listInvocationsInternal(): Promise<InvocationRecord[]> {
  const payload = await requestWithFallback<unknown>([
    { path: "/api/v1/invocations" },
  ]);
  return normalizeInvocationList(payload);
}

async function listProviderCatalogInternal(): Promise<ProviderTypeSpec[]> {
  const payload = await requestWithFallback<unknown>([
    { path: "/api/v1/providers/catalog" },
    { path: "/api/v1/provider-catalog" },
    { path: "/api/v1/catalog/providers" },
  ]);
  return normalizeProviderCatalog(payload);
}

async function listAgentTemplatesInternal(): Promise<AgentTemplate[]> {
  const payload = await requestWithFallback<unknown>([
    { path: "/api/v1/agents/templates" },
  ]);
  return normalizeTemplateList(payload);
}

function normalizeBootstrapPayload(
  payload: unknown,
  source: BootstrapPayload["source"],
): BootstrapPayload {
  const root = asRecord(payload);
  const bootstrap = asRecord(root.bootstrap) || root;
  const warning =
    readString(root, "warning") ?? readString(bootstrap, "warning");

  return {
    providers: normalizeProviderList(
      bootstrap.providers ?? root.providers ?? [],
    ),
    agents: normalizeAgentList(bootstrap.agents ?? root.agents ?? []),
    invocations: normalizeInvocationList(
      bootstrap.invocations ?? root.invocations ?? [],
    ),
    providerCatalog: normalizeProviderCatalog(
      bootstrap.providerCatalog ??
        bootstrap.provider_catalog ??
        root.providerCatalog ??
        root.provider_catalog ??
        [],
    ),
    agentTemplates: normalizeTemplateList(
      bootstrap.agentTemplates ??
        bootstrap.agent_templates ??
        root.agentTemplates ??
        root.agent_templates ??
        [],
    ),
    apiAvailable: true,
    source,
    warning,
  };
}

function normalizeProviderCatalog(payload: unknown): ProviderTypeSpec[] {
  const record = asRecord(payload);
  const source = Array.isArray(payload)
    ? payload
    : Array.isArray(record.providerCatalog)
      ? record.providerCatalog
      : Array.isArray(record.provider_catalog)
        ? record.provider_catalog
        : Array.isArray(record.items)
          ? record.items
          : Array.isArray(record.data)
            ? record.data
            : [];

  const normalized = source
    .map((item: unknown) => normalizeProviderTypeSpec(item))
    .filter((item) => item.key);

  return normalized.length > 0 ? normalized : DEFAULT_PROVIDER_CATALOG;
}

function normalizeProviderTypeSpec(payload: unknown): ProviderTypeSpec {
  const record = asRecord(payload);
  return {
    key: readString(record, "key", "providerType", "provider_type") ?? "",
    label:
      readString(record, "label") ?? readString(record, "key") ?? "Provider",
    description: readString(record, "description") ?? "",
    secretModes: normalizeStringArray(
      record.secretModes ?? record.secret_modes,
    ),
    defaultModel: readString(record, "defaultModel", "default_model") ?? "",
    modelExamples: normalizeStringArray(
      record.modelExamples ?? record.model_examples,
    ),
    apiBaseHint: readString(record, "apiBaseHint", "api_base_hint"),
    apiVersionHint: readString(record, "apiVersionHint", "api_version_hint"),
    requiresSecret:
      readBoolean(record, "requiresSecret", "requires_secret") ?? true,
    localOnlyHttp:
      readBoolean(record, "localOnlyHttp", "local_only_http") ?? false,
  };
}

function normalizeProviderList(payload: unknown): ProviderConfig[] {
  const record = asRecord(payload);
  const source = Array.isArray(payload)
    ? payload
    : Array.isArray(record.providers)
      ? record.providers
      : Array.isArray(record.items)
        ? record.items
        : Array.isArray(record.data)
          ? record.data
          : [];

  return sortProviders(
    source
      .map((item: unknown) => normalizeProvider(item))
      .filter((item) => item.id),
  );
}

function normalizeProvider(payload: unknown): ProviderConfig {
  const record = asRecord(payload);
  const secretMode = readString(record, "secretMode", "secret_mode") ?? "none";
  return {
    id: readString(record, "id") ?? "",
    name: readString(record, "name") ?? "",
    providerType: readString(record, "providerType", "provider_type") ?? "",
    enabled: readBoolean(record, "enabled") ?? true,
    defaultModel: readString(record, "defaultModel", "default_model") ?? "",
    apiBase: readString(record, "apiBase", "api_base"),
    apiVersion: readString(record, "apiVersion", "api_version"),
    organization: readString(record, "organization"),
    secretMode,
    secretEnvVar: readString(record, "secretEnvVar", "secret_env_var"),
    hasSecret:
      readBoolean(record, "hasSecret", "has_secret") ?? secretMode === "none",
    revision: readNumber(record, "revision") ?? 0,
    lastTestStatus:
      readString(record, "lastTestStatus", "last_test_status") ?? "unknown",
    lastTestError: readString(record, "lastTestError", "last_test_error"),
    lastTestedAt: readString(record, "lastTestedAt", "last_tested_at"),
    createdAt: readString(record, "createdAt", "created_at"),
    updatedAt: readString(record, "updatedAt", "updated_at"),
  };
}

function normalizeAgentList(payload: unknown): AgentConfig[] {
  const record = asRecord(payload);
  const source = Array.isArray(payload)
    ? payload
    : Array.isArray(record.agents)
      ? record.agents
      : Array.isArray(record.items)
        ? record.items
        : Array.isArray(record.data)
          ? record.data
          : [];

  return sortAgents(
    source
      .map((item: unknown) => normalizeAgent(item))
      .filter((item) => item.id),
  );
}

function normalizeAgent(payload: unknown): AgentConfig {
  const record = asRecord(payload);
  return {
    id: readString(record, "id") ?? "",
    slug: readString(record, "slug") ?? "",
    name: readString(record, "name") ?? "",
    description: readString(record, "description"),
    enabled: readBoolean(record, "enabled") ?? true,
    instructions: readString(record, "instructions") ?? "",
    reasoningMode:
      readString(record, "reasoningMode", "reasoning_mode") ?? "predict",
    inputFields: normalizeAgentInputFields(
      record.inputFields ?? record.input_fields,
    ),
    outputMode: readString(record, "outputMode", "output_mode") ?? "text",
    outputFieldName:
      readString(record, "outputFieldName", "output_field_name") ?? "response",
    outputSchema: normalizePlainObject(
      record.outputSchema ?? record.output_schema,
    ),
    defaultProviderId:
      readString(record, "defaultProviderId", "default_provider_id") ?? "",
    modelOverride: readString(record, "modelOverride", "model_override"),
    temperature: readNumber(record, "temperature") ?? 0.2,
    maxTokens: readNumber(record, "maxTokens", "max_tokens") ?? 700,
    revision: readNumber(record, "revision") ?? 0,
    createdAt: readString(record, "createdAt", "created_at"),
    updatedAt: readString(record, "updatedAt", "updated_at"),
  };
}

function normalizeAgentInputFields(payload: unknown): AgentInputField[] {
  if (!Array.isArray(payload)) {
    return [];
  }

  return payload.map((item: unknown) => {
    const record = asRecord(item);
    const name = readString(record, "name") ?? "";
    return {
      name,
      label: readString(record, "label") ?? humanizeIdentifier(name) ?? "Field",
      description: readString(record, "description"),
      required: readBoolean(record, "required") ?? false,
    };
  });
}

function normalizeTemplateList(payload: unknown): AgentTemplate[] {
  const record = asRecord(payload);
  const source = Array.isArray(payload)
    ? payload
    : Array.isArray(record.agentTemplates)
      ? record.agentTemplates
      : Array.isArray(record.agent_templates)
        ? record.agent_templates
        : Array.isArray(record.templates)
          ? record.templates
          : Array.isArray(record.items)
            ? record.items
            : Array.isArray(record.data)
              ? record.data
              : [];

  return source
    .map((item: unknown) => normalizeAgentTemplate(item))
    .filter((item) => item.id);
}

function normalizeAgentTemplate(payload: unknown): AgentTemplate {
  const record = asRecord(payload);
  return {
    id: readString(record, "id") ?? "",
    name: readString(record, "name") ?? "",
    description: readString(record, "description") ?? "",
    instructions: readString(record, "instructions") ?? "",
    inputFields: normalizeAgentInputFields(
      record.inputFields ?? record.input_fields,
    ),
    outputMode: readString(record, "outputMode", "output_mode") ?? "text",
    outputFieldName:
      readString(record, "outputFieldName", "output_field_name") ?? "response",
    outputSchema: normalizePlainObject(
      record.outputSchema ?? record.output_schema,
    ),
    reasoningMode:
      readString(record, "reasoningMode", "reasoning_mode") ?? "predict",
    temperature: readNumber(record, "temperature") ?? 0.2,
    maxTokens: readNumber(record, "maxTokens", "max_tokens") ?? 700,
  };
}

function normalizeInvocationList(payload: unknown): InvocationRecord[] {
  const record = asRecord(payload);
  const source = Array.isArray(payload)
    ? payload
    : Array.isArray(record.invocations)
      ? record.invocations
      : Array.isArray(record.items)
        ? record.items
        : Array.isArray(record.data)
          ? record.data
          : [];

  return sortInvocations(
    source
      .map((item: unknown) => normalizeInvocation(item))
      .filter((item) => item.id),
  );
}

function normalizeInvocation(payload: unknown): InvocationRecord {
  const record = asRecord(payload);
  return {
    id: readString(record, "id") ?? "",
    agentId: readString(record, "agentId", "agent_id") ?? "",
    agentRevision: readNumber(record, "agentRevision", "agent_revision") ?? 0,
    providerId: readString(record, "providerId", "provider_id") ?? "",
    providerRevision:
      readNumber(record, "providerRevision", "provider_revision") ?? 0,
    status: readString(record, "status") ?? "unknown",
    inputs: normalizePlainObject(record.inputs) ?? {},
    overrides: normalizePlainObject(record.overrides) ?? {},
    resolvedModel: readString(record, "resolvedModel", "resolved_model"),
    resolvedConfig:
      normalizePlainObject(record.resolvedConfig ?? record.resolved_config) ??
      {},
    outputText: readString(record, "outputText", "output_text"),
    outputJson: normalizePlainObject(record.outputJson ?? record.output_json),
    reasoningText: readString(record, "reasoningText", "reasoning_text"),
    usage: normalizePlainObject(record.usage),
    errorCode: readString(record, "errorCode", "error_code"),
    errorMessage: readString(record, "errorMessage", "error_message"),
    createdAt: readString(record, "createdAt", "created_at"),
    startedAt: readString(record, "startedAt", "started_at"),
    finishedAt: readString(record, "finishedAt", "finished_at"),
  };
}

function normalizeInvocationEventList(payload: unknown): InvocationEvent[] {
  const record = asRecord(payload);
  const source = Array.isArray(payload)
    ? payload
    : Array.isArray(record.events)
      ? record.events
      : Array.isArray(record.items)
        ? record.items
        : Array.isArray(record.data)
          ? record.data
          : [];

  return [...source]
    .map((item: unknown) => normalizeInvocationEvent(item))
    .sort((left, right) => left.seq - right.seq);
}

function normalizeInvocationEvent(payload: unknown): InvocationEvent {
  const record = asRecord(payload);
  return {
    seq: readNumber(record, "seq") ?? 0,
    type: readString(record, "type") ?? "",
    message: readString(record, "message") ?? "",
    payload: normalizePlainObject(record.payload) ?? {},
    createdAt: readString(record, "createdAt", "created_at"),
  };
}

function normalizeHealthSnapshot(payload: unknown): HealthSnapshot {
  const record = asRecord(payload);
  return {
    status: readString(record, "status"),
    version: readString(record, "version"),
    kernelEndpoint: readString(record, "kernelEndpoint", "kernel_endpoint"),
    httpBaseUrl: readString(record, "httpBaseUrl", "http_base_url"),
    shellUrl: readString(record, "shellUrl", "shell_url"),
    sessionId: readString(record, "sessionId", "session_id"),
    lastError: readString(record, "lastError", "last_error"),
    window: "window" in record ? normalizeWindowSnapshot(record.window) : null,
  };
}

function normalizeDependencySnapshot(payload: unknown): DependencySnapshot {
  const record = asRecord(payload);
  const rawDeps: unknown[] = Array.isArray(record.dependencies)
    ? record.dependencies
    : [];
  return {
    dependencies: rawDeps.map((dep: unknown) => {
      const d = asRecord(dep);
      return {
        name: readString(d, "name") ?? "unknown",
        state: readString(d, "state") ?? "DEPENDENCY_STATE_UNSPECIFIED",
        message: readString(d, "message") ?? "",
        detectedVersion: readString(d, "detectedVersion"),
        remediation: readString(d, "remediation"),
      };
    }),
    error: readString(record, "error") ?? undefined,
  };
}

function normalizeSessionSnapshot(payload: unknown): SessionSnapshot {
  const record = asRecord(payload);
  return {
    status: readString(record, "status"),
    kernelEndpoint: readString(record, "kernelEndpoint", "kernel_endpoint"),
    httpBaseUrl: readString(record, "httpBaseUrl", "http_base_url"),
    shellUrl: readString(record, "shellUrl", "shell_url"),
    sessionId: readString(record, "sessionId", "session_id"),
    grantedScopes: normalizeStringArray(
      record.grantedScopes ?? record.granted_scopes,
    ),
    lastRegisteredAtUnixMs: readNumber(
      record,
      "lastRegisteredAtUnixMs",
      "last_registered_at_unix_ms",
    ),
    lastHeartbeatAtUnixMs: readNumber(
      record,
      "lastHeartbeatAtUnixMs",
      "last_heartbeat_at_unix_ms",
    ),
    lastError: readString(record, "lastError", "last_error"),
    activeConfig: normalizeKernelActiveConfig(
      record.activeConfig ?? record.active_config,
    ),
  };
}

function normalizeKernelActiveConfig(
  payload: unknown,
): KernelActiveConfig | null {
  const record = asRecord(payload);
  if (Object.keys(record).length === 0) {
    return null;
  }

  const featuresSource = asRecord(record.features);
  const features = Object.fromEntries(
    Object.entries(featuresSource).map(([key, value]) => [key, String(value)]),
  );

  return {
    ipcEndpoint: readString(record, "ipcEndpoint", "ipc_endpoint"),
    bootId: readString(record, "bootId", "boot_id"),
    runtimeRoot: readString(record, "runtimeRoot", "runtime_root"),
    availableRuntimes: normalizeStringArray(
      record.availableRuntimes ?? record.available_runtimes,
    ),
    features,
  };
}

function normalizeWindowSnapshot(payload: unknown): WindowSnapshot {
  const record = asRecord(payload);
  return {
    backend: readString(record, "backend"),
    isOpen: readBoolean(record, "isOpen", "is_open") ?? false,
    openRequests: readNumber(record, "openRequests", "open_requests") ?? 0,
    lastOpenReason: readString(record, "lastOpenReason", "last_open_reason"),
    lastOpenedAtUnixMs: readNumber(
      record,
      "lastOpenedAtUnixMs",
      "last_opened_at_unix_ms",
    ),
    lastFocusedAtUnixMs: readNumber(
      record,
      "lastFocusedAtUnixMs",
      "last_focused_at_unix_ms",
    ),
    shellUrl: readString(record, "shellUrl", "shell_url"),
    loadedUrl: readString(record, "loadedUrl", "loaded_url"),
    lastLoadedAtUnixMs: readNumber(
      record,
      "lastLoadedAtUnixMs",
      "last_loaded_at_unix_ms",
    ),
  };
}

function normalizeKernelEvent(payload: unknown): KernelEventRecord {
  const record = asRecord(payload);
  const attributesSource = asRecord(record.attributes);
  const attributes = Object.fromEntries(
    Object.entries(attributesSource).map(([key, value]) => [
      key,
      String(value),
    ]),
  );

  return {
    eventId: readString(record, "eventId", "event_id") ?? "",
    eventType: readString(record, "eventType", "event_type") ?? "",
    resourceType: readString(record, "resourceType", "resource_type") ?? "",
    resourceId: readString(record, "resourceId", "resource_id") ?? "",
    status: readString(record, "status") ?? "",
    message: readString(record, "message") ?? "",
    timestampUnixMs:
      readNumber(record, "timestampUnixMs", "timestamp_unix_ms") ?? 0,
    attributes,
  };
}

async function requestWithFallback<T>(
  candidates: RequestCandidate[],
): Promise<T> {
  let lastError: unknown = null;

  for (const candidate of candidates) {
    try {
      return await requestJson<T>(candidate.path, {
        method: candidate.method ?? "GET",
        body:
          candidate.body === undefined
            ? undefined
            : JSON.stringify(candidate.body),
      });
    } catch (error) {
      if (
        error instanceof ApiError &&
        FALLBACK_STATUSES.has(error.status ?? -1)
      ) {
        lastError = error;
        continue;
      }
      throw error;
    }
  }

  throw lastError instanceof Error
    ? lastError
    : new ApiError("The requested API endpoint is not available.");
}

async function requestJson<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json");
  }
  if (init.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(path, {
    ...init,
    headers,
  });

  const text = await response.text();
  const payload = parseBody(text, response.headers.get("Content-Type"));

  if (!response.ok) {
    throw new ApiError(
      extractErrorMessage(payload, response.statusText),
      response.status,
      payload,
    );
  }

  return payload as T;
}

function parseBody(text: string, contentType: string | null): unknown {
  if (!text) {
    return null;
  }

  if (contentType?.includes("application/json")) {
    try {
      return JSON.parse(text);
    } catch {
      return text;
    }
  }

  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function extractErrorMessage(payload: unknown, fallback: string): string {
  if (typeof payload === "string" && payload.trim()) {
    return payload;
  }

  const record = asRecord(payload);
  return (
    (readString(
      record,
      "message",
      "error",
      "detail",
      "lastError",
      "last_error",
    ) ??
      fallback) ||
    "Request failed"
  );
}

function unwrapEntity(payload: unknown, keys: string[]): unknown {
  const record = asRecord(payload);
  for (const key of keys) {
    if (key in record) {
      return record[key];
    }
  }
  return payload;
}

function normalizePlainObject(value: unknown): Record<string, unknown> | null {
  return isRecord(value) ? value : null;
}

function normalizeStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((item: unknown) => String(item));
}

function readString(
  record: Record<string, unknown>,
  ...keys: string[]
): string | null {
  for (const key of keys) {
    const value = record[key];
    if (value === null || value === undefined) {
      continue;
    }
    if (typeof value === "string") {
      return value;
    }
    if (typeof value === "number" || typeof value === "boolean") {
      return String(value);
    }
  }
  return null;
}

function readNumber(
  record: Record<string, unknown>,
  ...keys: string[]
): number | null {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "number" && Number.isFinite(value)) {
      return value;
    }
    if (typeof value === "string" && value.trim()) {
      const parsed = Number(value);
      if (Number.isFinite(parsed)) {
        return parsed;
      }
    }
  }
  return null;
}

function readBoolean(
  record: Record<string, unknown>,
  ...keys: string[]
): boolean | null {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "boolean") {
      return value;
    }
    if (typeof value === "number") {
      return value !== 0;
    }
    if (typeof value === "string") {
      const normalized = value.trim().toLowerCase();
      if (["true", "1", "yes", "on"].includes(normalized)) {
        return true;
      }
      if (["false", "0", "no", "off"].includes(normalized)) {
        return false;
      }
    }
  }
  return null;
}

function toSortableTimestamp(
  value: string | number | null | undefined,
): number {
  if (typeof value === "number") {
    return value;
  }
  if (!value) {
    return 0;
  }
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
}

function humanizeIdentifier(value: string): string | null {
  if (!value) {
    return null;
  }
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(
      /(^|\s)(\w)/g,
      (_, prefix: string, char: string) => `${prefix}${char.toUpperCase()}`,
    );
}

function asRecord(value: unknown): Record<string, unknown> {
  return isRecord(value) ? value : {};
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
