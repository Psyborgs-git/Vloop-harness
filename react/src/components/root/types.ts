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
  component_id: string;
  config?: {
    input_map?: Record<string, string>;
  };
}

export interface Pipeline {
  id: string;
  name: string;
  description: string;
  steps: PipelineStep[];
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

export type NavTab = "chat" | "dspy" | "pipelines" | "settings";
