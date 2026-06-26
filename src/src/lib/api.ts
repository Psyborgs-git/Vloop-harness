// -- Re-export everything from sub-modules for backward compatibility --
export type {
  ProviderTypeKey,
  SecretMode,
  ReasoningMode,
  OutputMode,
  ProviderTypeSpec,
  ProviderConfig,
  AgentInputField,
  AgentConfig,
  AgentTemplate,
  InvocationRecord,
  InvocationEvent,
  UsageByProvider,
  UsageByAgent,
  RecentUsageInvocation,
  UsageStats,
  WindowSnapshot,
  HealthSnapshot,
  DependencyStatus,
  DependencySnapshot,
  KernelActiveConfig,
  SessionSnapshot,
  KernelEventRecord,
  SystemSnapshot,
  BootstrapPayload,
  ProviderMutationPayload,
  ProviderTestResult,
  AgentMutationPayload,
  AgentValidationResult,
  InvokeAgentRequest,
  ChatMessage,
  WorkloadSpec,
  WorkloadRecord,
  WorkloadLogLine,
  WorkloadLogsResponse,
  DatabaseSettings,
} from "./types";

export { DEFAULT_PROVIDER_CATALOG } from "./types";
export { ApiError, getErrorMessage } from "./api-client";
export {
  sortProviders,
  sortAgents,
  sortInvocations,
  sortKernelEvents,
  isTerminalInvocationStatus,
} from "./helpers";

// System/bootstrap endpoints
export {
  getBootstrap,
  getSystemSnapshot,
  shutdownApp,
  getDatabaseSettings,
  saveDatabaseSettings,
  testDatabaseConnection,
  getUsageStats,
} from "./endpoints/system";

// Provider CRUD endpoints
export {
  saveProvider,
  testProvider,
  deleteProvider,
} from "./endpoints/provider";

// Agent CRUD + invocation endpoints
export {
  listAgentTemplates,
  validateAgent,
  saveAgent,
  deleteAgent,
  listInvocations,
  getInvocation,
  getInvocationEvents,
  invokeAgent,
  chatWithAgent,
} from "./endpoints/agent";

// Workload endpoints
export {
  listWorkloads,
  createWorkload,
  startWorkload,
  stopWorkload,
  getWorkloadLogs,
} from "./endpoints/workloads";
