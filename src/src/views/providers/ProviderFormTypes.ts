import type { SecretMode } from "../../lib/api";

export interface ProviderFormState {
  id: string | null;
  name: string;
  providerType: string;
  enabled: boolean;
  defaultModel: string;
  apiBase: string;
  apiVersion: string;
  organization: string;
  secretMode: SecretMode;
  secretEnvVar: string;
  sessionSecret: string;
  hasSecret: boolean;
  revision: number;
  lastTestStatus: string;
  lastTestError: string;
  lastTestedAt: string;
  createdAt: string;
  updatedAt: string;
}

export interface ProviderValidation {
  fieldErrors: Partial<
    Record<
      | "name"
      | "defaultModel"
      | "secretEnvVar"
      | "sessionSecret"
      | "apiBase"
      | "secretMode",
      string
    >
  >;
  formError: string | null;
}
