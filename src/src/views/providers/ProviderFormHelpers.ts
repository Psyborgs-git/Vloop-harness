import type { ProviderConfig, ProviderTypeSpec } from "../../lib/api";
import type {
  ProviderFormState,
  ProviderValidation,
} from "./ProviderFormTypes";

/** Convert an empty/whitespace string (or null) to null, otherwise return trimmed. */
export function emptyToNull(value: string | null | undefined): string | null {
  if (!value) return null;
  return value.trim() ? value.trim() : null;
}

/** Convert a ProviderConfig from the API into local form state. */
export function providerToForm(provider: ProviderConfig): ProviderFormState {
  return {
    id: provider.id,
    name: provider.name,
    providerType: provider.providerType,
    enabled: provider.enabled,
    defaultModel: provider.defaultModel,
    apiBase: provider.apiBase ?? "",
    apiVersion: provider.apiVersion ?? "",
    organization: provider.organization ?? "",
    secretMode: provider.secretMode,
    secretEnvVar: provider.secretEnvVar ?? "",
    sessionSecret: "",
    hasSecret: provider.hasSecret,
    revision: provider.revision,
    lastTestStatus: provider.lastTestStatus,
    lastTestError: provider.lastTestError ?? "",
    lastTestedAt: provider.lastTestedAt ?? "",
    createdAt: provider.createdAt ?? "",
    updatedAt: provider.updatedAt ?? "",
  };
}

/** Create a fresh default provider form draft based on a catalog spec. */
export function createDraft(spec: ProviderTypeSpec): ProviderFormState {
  return {
    id: null,
    name: "",
    providerType: spec.key,
    enabled: true,
    defaultModel: spec.defaultModel,
    apiBase: spec.apiBaseHint ?? "",
    apiVersion: spec.apiVersionHint ?? "",
    organization: "",
    secretMode: spec.secretModes[0] ?? "none",
    secretEnvVar: "",
    sessionSecret: "",
    hasSecret: spec.secretModes[0] === "none",
    revision: 0,
    lastTestStatus: "unknown",
    lastTestError: "",
    lastTestedAt: "",
    createdAt: "",
    updatedAt: "",
  };
}

/** Validate the provider form and return field-level + form-level errors. */
export function validateProviderForm(
  form: ProviderFormState,
  spec: ProviderTypeSpec,
): ProviderValidation {
  const fieldErrors: ProviderValidation["fieldErrors"] = {};

  if (form.name.trim().length < 2) {
    fieldErrors.name = "Provider names must be at least 2 characters.";
  }
  if (!form.defaultModel.trim()) {
    fieldErrors.defaultModel =
      "Enter the default model string the Control Plane should resolve.";
  }
  if (!spec.secretModes.includes(form.secretMode)) {
    fieldErrors.secretMode = `This provider type supports: ${spec.secretModes.join(", ")}.`;
  }
  if (form.secretMode === "env" && !form.secretEnvVar.trim()) {
    fieldErrors.secretEnvVar =
      "Enter the environment variable that holds this provider secret.";
  }
  if (form.secretMode === "session" && !form.id && !form.sessionSecret.trim()) {
    fieldErrors.sessionSecret =
      "New session-secret providers need a secret before they can be saved.";
  }
  if (
    form.apiBase.trim() &&
    form.apiBase.startsWith("http://") &&
    !spec.localOnlyHttp
  ) {
    fieldErrors.apiBase = "Remote provider API bases must use https://.";
  }
  if (
    spec.localOnlyHttp &&
    form.apiBase.trim() &&
    !/^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/i.test(form.apiBase.trim())
  ) {
    fieldErrors.apiBase =
      "Ollama API bases must point at http://127.0.0.1 or http://localhost.";
  }

  const formError = Object.keys(fieldErrors).length
    ? "The provider form has invalid or missing values."
    : null;

  return { fieldErrors, formError };
}

/** Serialize form to JSON for dirty-check comparison. */
export function serializeForm(form: ProviderFormState): string {
  return JSON.stringify({
    id: form.id,
    name: form.name,
    providerType: form.providerType,
    enabled: form.enabled,
    defaultModel: form.defaultModel,
    apiBase: form.apiBase,
    apiVersion: form.apiVersion,
    organization: form.organization,
    secretMode: form.secretMode,
    secretEnvVar: form.secretEnvVar,
    sessionSecret: form.sessionSecret,
  });
}
