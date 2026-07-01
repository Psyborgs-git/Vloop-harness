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
  elapsedMs: number | null;
  createdAt: string | null;
}

export interface UsageByProvider {
  providerId: string;
  providerName: string;
  providerType: string;
  invocationCount: number;
  totalTokens: number;
}

export interface UsageByAgent {
  agentId: string;
  agentName: string;
  invocationCount: number;
  totalTokens: number;
}

export interface RecentUsageInvocation {
  invocationId: string;
  agentId: string;
  agentName: string;
  providerId: string;
  providerName: string;
  providerType: string;
  model: string;
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
  createdAt: string | null;
}

export interface UsageStats {
  totalTokens: number;
  totalPromptTokens: number;
  totalCompletionTokens: number;
  invocationCount: number;
  byProvider: UsageByProvider[];
  byAgent: UsageByAgent[];
  recentInvocations: RecentUsageInvocation[];
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

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
  timestamp?: string;
}

export interface RequestCandidate {
  path: string;
  method?: string;
  body?: unknown;
}

// -- Workload types --

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

// -- Workflow orchestration types --
// These mirror the Control_Plane workflow APIs (cp/handlers/workflows.py) and
// the normalized WorkflowEvent frames streamed over the WebSocket channel
// (core/event_router.py). Run/step/event payloads come straight from the
// Control_Plane as snake_case dicts, so those shapes are kept snake_case to
// match the wire format exactly.

export interface WorkflowDefinition {
  id: string;
  name: string;
  objective: string;
  definition: Record<string, unknown>;
  revision: number;
  createdAt: string | null;
  updatedAt: string | null;
}

export interface WorkflowValidationResult {
  valid: boolean;
  problems: unknown[];
}

export interface WorkflowTemplate {
  id: string;
  name: string;
  description?: string;
  definition: Record<string, unknown>;
  [key: string]: unknown;
}

export interface WorkflowRun {
  id: string;
  definition_id: string;
  state: string;
  concurrency_limit: number;
  budget_json: string | null;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface WorkflowStep {
  run_id: string;
  step_id: string;
  step_type: string;
  state: string;
  depends_on_json: string;
  inputs_json: string | null;
  output_json: string | null;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
}

/** A normalized workflow event frame as streamed over the WebSocket channel. */
export interface WorkflowEventFrame {
  run_id: string;
  seq: number;
  type: string;
  step_id: string | null;
  message: string;
  payload: Record<string, unknown>;
  created_at: string;
}

/** The run-observation response: current state, step states, and history. */
export interface WorkflowRunObservation {
  run: WorkflowRun;
  steps: WorkflowStep[];
  events: WorkflowEventFrame[];
}

/**
 * A checkpoint awaiting a user decision, as returned by the Control_Plane
 * pending-approvals API (cp/handlers/approvals.py). `context` mirrors the
 * checkpoint context streamed with the `approval.required` event.
 */
export interface PendingApproval {
  run_id: string;
  step_id: string;
  context: Record<string, unknown>;
}

/**
 * A recorded workspace Checkpoint for a Workflow_Run, as returned by the
 * Control_Plane checkpoints API (cp/handlers/checkpoints.py). The
 * Checkpoint_Manager records only metadata plus the opaque kernel snapshot
 * reference — never file contents (Req 13.1, 13.4). Fields are snake_case to
 * match the wire format exactly.
 */
export interface Checkpoint {
  id: string;
  run_id: string;
  workspace_id: string;
  kernel_snapshot_ref: string;
  created_at: string | null;
}

/**
 * A Scheduled_Task as returned by the Control_Plane schedules API
 * (cp/handlers/schedules.py). A schedule triggers Workflow_Runs for a workflow
 * definition on a cron cadence and may be `active` or `paused` (Req 14.1, 14.3).
 * Fields are snake_case to match the wire format exactly. `next_run_at` is the
 * informational next trigger time (null while paused or when nothing matches).
 */
export type ScheduledTaskState = "active" | "paused";

export interface ScheduledTask {
  id: string;
  definition_id: string;
  cron_expression: string;
  state: ScheduledTaskState | string;
  next_run_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

// -- Database settings --

export interface DatabaseSettings {
  databaseUrl: string;
  vectorDbUrl: string;
  activeBackend: string;
  vectorStoreActive: string;
}

// -- Shared constants --

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
