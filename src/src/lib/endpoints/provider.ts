import type { ProviderConfig, ProviderMutationPayload, ProviderTestResult, ProviderTypeSpec } from "../types";
import { DEFAULT_PROVIDER_CATALOG } from "../types";
import { requestJson, requestWithFallback, unwrapEntity } from "../api-client";
import { normalizeProvider, normalizeProviderList, normalizeProviderCatalog } from "../normalizers";

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

  function asRecord(v: unknown): Record<string, unknown> {
    return typeof v === "object" && v !== null && !Array.isArray(v)
      ? (v as Record<string, unknown>)
      : {};
  }

  function readString(record: Record<string, unknown>, ...keys: string[]): string | null {
    for (const key of keys) {
      const value = record[key];
      if (typeof value === "string") return value;
      if (typeof value === "number" || typeof value === "boolean") return String(value);
    }
    return null;
  }

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

export async function listProvidersInternal(): Promise<ProviderConfig[]> {
  const payload = await requestWithFallback<unknown>([
    { path: "/api/v1/providers" },
  ]);
  return normalizeProviderList(payload);
}

export async function listProviderCatalogInternal(): Promise<ProviderTypeSpec[]> {
  const payload = await requestWithFallback<unknown>([
    { path: "/api/v1/providers/catalog" },
    { path: "/api/v1/provider-catalog" },
    { path: "/api/v1/catalog/providers" },
  ]);
  return normalizeProviderCatalog(payload);
}
