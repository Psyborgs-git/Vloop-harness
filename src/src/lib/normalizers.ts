import type {
  AgentConfig,
  AgentInputField,
  AgentTemplate,
  BootstrapPayload,
  InvocationEvent,
  InvocationRecord,
  KernelActiveConfig,
  KernelEventRecord,
  HealthSnapshot,
  DependencySnapshot,
  SessionSnapshot,
  WindowSnapshot,
  ProviderConfig,
  ProviderTypeSpec,
  RecentUsageInvocation,
  UsageByAgent,
  UsageByProvider,
  UsageStats,
  WorkloadRecord,
} from "./types";
import { DEFAULT_PROVIDER_CATALOG } from "./types";
import {
  normalizePlainObject,
  normalizeStringArray,
  readBoolean,
  readNumber,
  readString,
} from "./api-client";

/* ── Value-safe readers (accept unknown, return with fallback) ── */
function readStr(value: unknown, fallback: string): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean")
    return String(value);
  return fallback;
}
function readNum(value: unknown, fallback: number): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const p = Number(value);
    if (Number.isFinite(p)) return p;
  }
  return fallback;
}
function readBool(value: unknown, fallback: boolean): boolean {
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value !== 0;
  if (typeof value === "string") {
    const n = value.trim().toLowerCase();
    if (["true", "1", "yes", "on"].includes(n)) return true;
    if (["false", "0", "no", "off"].includes(n)) return false;
  }
  return fallback;
}

import {
  humanizeIdentifier,
  sortAgents,
  sortInvocations,
  sortKernelEvents,
  sortProviders,
} from "./helpers";

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

export function normalizeBootstrapPayload(
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

export function normalizeProviderCatalog(payload: unknown): ProviderTypeSpec[] {
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

export function normalizeProviderTypeSpec(payload: unknown): ProviderTypeSpec {
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

export function normalizeProviderList(payload: unknown): ProviderConfig[] {
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

export function normalizeProvider(payload: unknown): ProviderConfig {
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

export function normalizeAgentList(payload: unknown): AgentConfig[] {
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

export function normalizeAgent(payload: unknown): AgentConfig {
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

export function normalizeAgentInputFields(payload: unknown): AgentInputField[] {
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

export function normalizeTemplateList(payload: unknown): AgentTemplate[] {
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

export function normalizeAgentTemplate(payload: unknown): AgentTemplate {
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

export function normalizeInvocationList(payload: unknown): InvocationRecord[] {
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

export function normalizeInvocation(payload: unknown): InvocationRecord {
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

export function normalizeInvocationEventList(
  payload: unknown,
): InvocationEvent[] {
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

export function normalizeInvocationEvent(payload: unknown): InvocationEvent {
  const record = asRecord(payload);
  return {
    seq: readNumber(record, "seq") ?? 0,
    type: readString(record, "type") ?? "",
    message: readString(record, "message") ?? "",
    payload: normalizePlainObject(record.payload) ?? {},
    elapsedMs: readNumber(record, "elapsedMs", "elapsed_ms"),
    createdAt: readString(record, "createdAt", "created_at"),
  };
}

export function normalizeUsageStats(payload: unknown): UsageStats {
  const record = asRecord(payload);
  const byProvider: UsageByProvider[] = (
    Array.isArray(record.byProvider) ? record.byProvider : []
  ).map((item: unknown) => {
    const p = asRecord(item);
    return {
      providerId: readString(p, "providerId", "provider_id") ?? "",
      providerName: readString(p, "providerName", "provider_name") ?? "",
      providerType: readString(p, "providerType", "provider_type") ?? "",
      invocationCount:
        readNumber(p, "invocationCount", "invocation_count") ?? 0,
      totalTokens: readNumber(p, "totalTokens", "total_tokens") ?? 0,
    };
  });
  const byAgent: UsageByAgent[] = (
    Array.isArray(record.byAgent) ? record.byAgent : []
  ).map((item: unknown) => {
    const a = asRecord(item);
    return {
      agentId: readString(a, "agentId", "agent_id") ?? "",
      agentName: readString(a, "agentName", "agent_name") ?? "",
      invocationCount:
        readNumber(a, "invocationCount", "invocation_count") ?? 0,
      totalTokens: readNumber(a, "totalTokens", "total_tokens") ?? 0,
    };
  });
  const recentInvocations: RecentUsageInvocation[] = (
    Array.isArray(record.recentInvocations) ? record.recentInvocations : []
  ).map((item: unknown) => {
    const r = asRecord(item);
    return {
      invocationId: readString(r, "invocationId", "invocation_id") ?? "",
      agentId: readString(r, "agentId", "agent_id") ?? "",
      agentName: readString(r, "agentName", "agent_name") ?? "",
      providerId: readString(r, "providerId", "provider_id") ?? "",
      providerName: readString(r, "providerName", "provider_name") ?? "",
      providerType: readString(r, "providerType", "provider_type") ?? "",
      model: readString(r, "model") ?? "",
      promptTokens: readNumber(r, "promptTokens", "prompt_tokens") ?? 0,
      completionTokens:
        readNumber(r, "completionTokens", "completion_tokens") ?? 0,
      totalTokens: readNumber(r, "totalTokens", "total_tokens") ?? 0,
      createdAt: readString(r, "createdAt", "created_at"),
    };
  });
  return {
    totalTokens: readNumber(record, "totalTokens", "total_tokens") ?? 0,
    totalPromptTokens:
      readNumber(record, "totalPromptTokens", "total_prompt_tokens") ?? 0,
    totalCompletionTokens:
      readNumber(record, "totalCompletionTokens", "total_completion_tokens") ??
      0,
    invocationCount:
      readNumber(record, "invocationCount", "invocation_count") ?? 0,
    byProvider,
    byAgent,
    recentInvocations,
  };
}

export function normalizeHealthSnapshot(payload: unknown): HealthSnapshot {
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

export function normalizeDependencySnapshot(
  payload: unknown,
): DependencySnapshot {
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

export function normalizeSessionSnapshot(payload: unknown): SessionSnapshot {
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

export function normalizeKernelActiveConfig(
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

export function normalizeKernelEvent(payload: unknown): KernelEventRecord {
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

export { normalizeWindowSnapshot };

export function normalizeWorkloadRecord(input: unknown): WorkloadRecord {
  const record = asRecord(input);
  const rawSpec = asRecord(record.spec);
  return {
    workloadId: readStr(record.workloadId, ""),
    class: readStr(record.class, "unspecified"),
    state: readStr(record.state, "unspecified"),
    spec: {
      image: readStr(rawSpec.image, ""),
      command: normalizeStringArray(rawSpec.command),
      ports: normalizeStringArray(rawSpec.ports).map(Number),
      environment: asRecord(rawSpec.environment) as Record<string, string>,
    },
    createdAtUnixMs: readNum(record.createdAtUnixMs, 0),
    updatedAtUnixMs: readNum(record.updatedAtUnixMs, 0),
    exitCode: record.exitCode != null ? readNum(record.exitCode, 0) : null,
    terminationReason: readStr(record.terminationReason, ""),
    exposedPorts: normalizeStringArray(record.exposedPorts).map(Number),
    previewUrl: readStr(record.previewUrl, ""),
  };
}
