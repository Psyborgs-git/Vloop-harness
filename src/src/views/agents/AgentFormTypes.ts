import type { AgentInputField } from "../../lib/api";

export interface AgentFieldState extends AgentInputField {
  id: string;
}

export interface AgentFormState {
  id: string | null;
  name: string;
  slug: string;
  description: string;
  instructions: string;
  reasoningMode: "predict" | "chain_of_thought";
  inputFields: AgentFieldState[];
  outputMode: "text" | "json";
  outputFieldName: string;
  outputSchemaText: string;
  defaultProviderId: string;
  modelOverride: string;
  temperature: string;
  maxTokens: string;
  enabled: boolean;
  revision: number;
  createdAt: string;
  updatedAt: string;
}

export interface AgentValidationState {
  fieldErrors: Partial<
    Record<
      | "name"
      | "slug"
      | "instructions"
      | "outputFieldName"
      | "outputSchemaText"
      | "defaultProviderId"
      | "temperature"
      | "maxTokens"
      | `field-name-${string}`
      | `field-label-${string}`,
      string
    >
  >;
  formError: string | null;
  parsedOutputSchema: Record<string, unknown> | null;
}
