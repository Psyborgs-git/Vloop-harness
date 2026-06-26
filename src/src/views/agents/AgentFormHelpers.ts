import type { AgentConfig, ProviderConfig } from "../../lib/api";
import type { AgentFormState, AgentValidationState } from "./AgentFormTypes";

/** Generate a unique local ID for input fields (used in forms, not persisted). */
export function createLocalId(): string {
  return `field-${Math.random().toString(36).slice(2, 10)}`;
}

/** Convert a string into a URL-friendly slug. */
export function slugify(value: string): string {
  const slug = value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug || "agent";
}

/** Turn a snake_case or kebab-case identifier into a human-readable label. */
export function humanize(value: string): string | null {
  if (!value) {
    return null;
  }
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(
      /(^|\s)(\w)/g,
      (_: string, prefix: string, char: string) =>
        `${prefix}${char.toUpperCase()}`,
    );
}

/** Convert an empty/whitespace string (or null) to null, otherwise return trimmed. */
export function emptyToNull(value: string | null | undefined): string | null {
  if (!value) return null;
  return value.trim() ? value.trim() : null;
}

/** Create a fresh default agent form draft. */
export function createDraft(defaultProviderId: string): AgentFormState {
  return {
    id: null,
    name: "",
    slug: "",
    description: "",
    instructions: "",
    reasoningMode: "predict",
    inputFields: [
      {
        id: createLocalId(),
        name: "input_text",
        label: "Input text",
        description: "",
        required: true,
      },
    ],
    outputMode: "text",
    outputFieldName: "response",
    outputSchemaText: "",
    defaultProviderId,
    modelOverride: "",
    temperature: "0.2",
    maxTokens: "700",
    enabled: true,
    revision: 0,
    createdAt: "",
    updatedAt: "",
  };
}

/** Convert an AgentConfig from the API into local form state. */
export function agentToForm(
  agent: AgentConfig,
  fallbackProviderId: string,
): AgentFormState {
  return {
    id: agent.id,
    name: agent.name,
    slug: agent.slug,
    description: agent.description ?? "",
    instructions: agent.instructions,
    reasoningMode:
      agent.reasoningMode === "chain_of_thought"
        ? "chain_of_thought"
        : "predict",
    inputFields: agent.inputFields.map((field) => ({
      ...field,
      id: createLocalId(),
      description: field.description ?? "",
    })),
    outputMode: agent.outputMode === "json" ? "json" : "text",
    outputFieldName: agent.outputFieldName,
    outputSchemaText: agent.outputSchema
      ? JSON.stringify(agent.outputSchema, null, 2)
      : "",
    defaultProviderId: agent.defaultProviderId || fallbackProviderId,
    modelOverride: agent.modelOverride ?? "",
    temperature: String(agent.temperature),
    maxTokens: String(agent.maxTokens),
    enabled: agent.enabled,
    revision: agent.revision,
    createdAt: agent.createdAt ?? "",
    updatedAt: agent.updatedAt ?? "",
  };
}

/** Serialize form to JSON for dirty-check comparison. */
export function serializeForm(form: AgentFormState): string {
  return JSON.stringify({
    id: form.id,
    name: form.name,
    slug: form.slug,
    description: form.description,
    instructions: form.instructions,
    reasoningMode: form.reasoningMode,
    inputFields: form.inputFields.map(({ id: _, ...field }) => field),
    outputMode: form.outputMode,
    outputFieldName: form.outputFieldName,
    outputSchemaText: form.outputSchemaText,
    defaultProviderId: form.defaultProviderId,
    modelOverride: form.modelOverride,
    temperature: form.temperature,
    maxTokens: form.maxTokens,
    enabled: form.enabled,
  });
}

/** Validate the agent form and return field-level + form-level errors. */
export function validateAgentForm(
  form: AgentFormState,
  providers: ProviderConfig[],
): AgentValidationState {
  const fieldErrors: AgentValidationState["fieldErrors"] = {};

  if (form.name.trim().length < 2) {
    fieldErrors.name = "Agent names must be at least 2 characters.";
  }
  if (!/^[a-z0-9][a-z0-9-]*$/.test(form.slug.trim())) {
    fieldErrors.slug =
      "Slugs may only use lowercase letters, numbers, and hyphens.";
  }
  if (form.instructions.trim().length < 10) {
    fieldErrors.instructions = "Instructions must be at least 10 characters.";
  }
  if (!/^[a-zA-Z][a-zA-Z0-9_]*$/.test(form.outputFieldName.trim())) {
    fieldErrors.outputFieldName =
      "Use a safe identifier such as response or summary_json.";
  }

  const seenNames = new Set<string>();
  form.inputFields.forEach((field) => {
    const trimmedName = field.name.trim();
    if (!/^[a-zA-Z][a-zA-Z0-9_]*$/.test(trimmedName)) {
      fieldErrors[`field-name-${field.id}`] =
        "Use a safe identifier such as source_text.";
    } else if (seenNames.has(trimmedName)) {
      fieldErrors[`field-name-${field.id}`] =
        "Field names must be unique within the agent.";
    }
    seenNames.add(trimmedName);

    if (!field.label.trim() && !trimmedName) {
      fieldErrors[`field-label-${field.id}`] =
        "Add a label or name so the playground can render this field.";
    }
  });

  if (form.inputFields.length === 0) {
    fieldErrors["field-name-empty"] = "Add at least one input field.";
  }

  if (!providers.some((provider) => provider.id === form.defaultProviderId)) {
    fieldErrors.defaultProviderId = "Select an existing default provider.";
  }

  if (
    form.temperature.trim() === "" ||
    Number.isNaN(Number(form.temperature))
  ) {
    fieldErrors.temperature = "Enter a numeric temperature, such as 0.2.";
  }

  if (
    form.maxTokens.trim() === "" ||
    !Number.isInteger(Number(form.maxTokens)) ||
    Number(form.maxTokens) < 32
  ) {
    fieldErrors.maxTokens = "Max tokens must be an integer of at least 32.";
  }

  let parsedOutputSchema: Record<string, unknown> | null = null;
  if (form.outputMode === "json") {
    if (!form.outputSchemaText.trim()) {
      fieldErrors.outputSchemaText =
        "JSON output agents need a non-empty output schema object.";
    } else {
      try {
        const parsed = JSON.parse(form.outputSchemaText);
        if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
          fieldErrors.outputSchemaText =
            "The output schema must be a JSON object at the top level.";
        } else {
          parsedOutputSchema = parsed as Record<string, unknown>;
        }
      } catch {
        fieldErrors.outputSchemaText = "The output schema must be valid JSON.";
      }
    }
  }

  const formError = Object.keys(fieldErrors).length
    ? "The agent form has invalid or missing values."
    : null;

  return { fieldErrors, formError, parsedOutputSchema };
}
