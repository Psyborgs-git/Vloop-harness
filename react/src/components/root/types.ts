/** Shared TypeScript types for the VLoop dashboard UI. */

export interface ChatSession {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  id: string;
  session_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  meta: {
    component_code?: string;
    saved_component_id?: string;
    pipeline_config?: string;
    saved_pipeline_id?: string;
    view_stub_request?: string;
    saved_view_id?: string;
  };
  created_at: string;
}

export interface DSPyComponent {
  id: string;
  name: string;
  description: string;
  signature_fields: {
    inputs: Array<{ name: string; desc: string }>;
    outputs: Array<{ name: string; desc: string }>;
  };
  code: string;
  module_type: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface PipelineStep {
  type?: "component" | "tool";
  component_id?: string;
  tool_name?: string;
  config?: {
    input_map?: Record<string, string>;
    command?: string;
    cwd_relative?: string;
    timeout?: number;
    [key: string]: unknown;
  };
}

export interface Pipeline {
  id: string;
  name: string;
  description: string;
  steps: PipelineStep[];
  tool_permissions?: string[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Provider {
  id: string;
  name: string;
  provider_type: "ollama" | "anthropic" | "openai" | "custom";
  model: string;
  base_url: string;
  has_api_key: boolean;
  extra_config: Record<string, unknown>;
  is_default: boolean;
  created_at: string;
}

export interface RunResult {
  inputs: Record<string, string>;
  outputs: Record<string, unknown>;
}

/** Panel shown in the right contextual drawer. */
export type ContextPanelType = "dspy" | "pipelines" | "tools" | "view" | "agents" | "manifests" | "eval" | null;

export interface ContextPanelState {
  type: ContextPanelType;
  id?: string;
}

// ── Generated view types ───────────────────────────────────────────────────

export interface GeneratedView {
  id: string;
  name: string;
  component_name: string;
  react_code: string;
  view_spec: string;
  file_path: string | null;
  session_id: string | null;
  created_at: string;
}

// ── Tool types ─────────────────────────────────────────────────────────────

export interface ToolCatalogEntry {
  name: string;
  description: string;
  required_permission: string;
  risk_level: "safe" | "caution" | "destructive";
}

export interface ToolResult {
  success: boolean;
  output: string;
  error: string | null;
  exit_code: number | null;
  metadata: Record<string, unknown>;
}

export interface ConfirmationRequest {
  requires_confirmation: true;
  token: string;
  description: string;
  risk_level: "caution" | "destructive";
  expires_in_seconds: number;
}

export interface DirectoryPolicy {
  directory: string;
  allowed_commands: string[];
  allowed_arg_patterns: Record<string, string[]>;
  max_runtime_seconds: number;
  max_output_bytes: number;
}

export interface PolicyConfig {
  permanent_blocklist: string[];
  denylist: string[];
  directories: DirectoryPolicy[];
}

export interface FilesystemEntry {
  name: string;
  type: "file" | "dir" | "unknown";
  size?: number;
  mtime?: number;
}

// ── Agent runs ─────────────────────────────────────────────────────────────

export interface AgentRunStep {
  id: string;
  run_id: string;
  step_type: string;
  tool_name: string | null;
  input_data: Record<string, unknown> | null;
  output_data: Record<string, unknown> | null;
  status: "pending" | "running" | "completed" | "failed" | "skipped";
  error: string | null;
  confirmation_token: string | null;
  duration_ms: number | null;
  created_at: string;
}

export interface AgentRun {
  id: string;
  goal: string;
  plan: string;
  status: "pending" | "running" | "paused" | "completed" | "cancelled" | "failed";
  autonomy_mode: "observe" | "suggest" | "write_approval" | "test_approval" | "autonomous";
  session_id: string | null;
  result: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
  updated_at: string;
  steps?: AgentRunStep[];
}

// ── Workspace windows ─────────────────────────────────────────────────────

export interface WorkspaceWindow {
  id: string;
  title: string;
  url: string;
  minimized: boolean;
  focusedAt: number;
}

// ── App manifests ──────────────────────────────────────────────────────────

export interface AppManifest {
  id: string;
  name: string;
  description: string;
  backend_type: "component" | "pipeline" | "dspy_module";
  backend_id: string | null;
  react_views: string[];
  permissions: string[];
  state_schema: Record<string, unknown>;
  status: "draft" | "validated" | "active" | "archived";
  agent_run_id: string | null;
  created_at: string;
  updated_at: string;
}

// ── Tool traces ────────────────────────────────────────────────────────────

export interface ToolTrace {
  id: string;
  tool_name: string;
  component_id: string | null;
  session_id: string | null;
  run_step_id: string | null;
  inputs: Record<string, unknown> | null;
  outputs: Record<string, unknown> | null;
  risk_level: "safe" | "caution" | "destructive";
  confirmation_token: string | null;
  duration_ms: number | null;
  success: boolean;
  created_at: string;
}

