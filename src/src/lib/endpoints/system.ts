import type {
  BootstrapPayload,
  SystemSnapshot,
  UsageStats,
  InvocationEvent,
  DatabaseSettings,
} from "../types";
import { DEFAULT_PROVIDER_CATALOG } from "../types";
import { requestJson, requestWithFallback } from "../api-client";
import {
  normalizeBootstrapPayload,
  normalizeHealthSnapshot,
  normalizeSessionSnapshot,
  normalizeWindowSnapshot,
  normalizeKernelEvent,
  normalizeDependencySnapshot,
  normalizeUsageStats,
} from "../normalizers";
import { sortKernelEvents } from "../helpers";
import { readBoolean, readNumber, readString, normalizePlainObject } from "../api-client";
import { listProvidersInternal, listProviderCatalogInternal } from "./provider";
import { listAgentsInternal, listInvocationsInternal, listAgentTemplatesInternal } from "./agent";

export async function getBootstrap(): Promise<BootstrapPayload> {
  const FALLBACK_STATUSES = new Set([404, 405]);

  try {
    const payload = await requestWithFallback<unknown>([
      { path: "/api/v1/bootstrap" },
      { path: "/api/v1" },
      { path: "/api/v1/state" },
    ]);

    let bootstrap = normalizeBootstrapPayload(payload, "bootstrap");
    if (bootstrap.agentTemplates.length === 0) {
      try {
        bootstrap = {
          ...bootstrap,
          agentTemplates: await listAgentTemplatesInternal(),
        };
      } catch {
        // Best-effort only.
      }
    }
    return bootstrap;
  } catch (error) {
    if (
      error instanceof Error &&
      "status" in error &&
      FALLBACK_STATUSES.has((error as { status: number }).status ?? -1)
    ) {
      return assembleBootstrapFromIndividualEndpoints();
    }
    throw error;
  }
}

export async function getSystemSnapshot(): Promise<SystemSnapshot> {
  const [
    healthPayload,
    sessionPayload,
    windowPayload,
    eventsPayload,
    depsPayload,
  ] = await Promise.all([
    requestJson<unknown>("/health"),
    requestJson<unknown>("/session"),
    requestJson<unknown>("/window"),
    requestJson<unknown>("/events/recent"),
    requestJson<unknown>("/dependencies"),
  ]);

  const eventsRecord = asRecord(eventsPayload);
  const recentEventsSource = Array.isArray(eventsPayload)
    ? eventsPayload
    : Array.isArray(eventsRecord.recentEvents)
      ? eventsRecord.recentEvents
      : Array.isArray(eventsRecord.recent_events)
        ? eventsRecord.recent_events
        : [];

  const recentEvents = sortKernelEvents(
    recentEventsSource.map((event: unknown) => normalizeKernelEvent(event)),
  );

  return {
    health: normalizeHealthSnapshot(healthPayload),
    session: normalizeSessionSnapshot(sessionPayload),
    window: normalizeWindowSnapshot(windowPayload),
    dependencies: normalizeDependencySnapshot(depsPayload),
    recentEvents,
    eventCount:
      readNumber(eventsRecord, "eventCount", "event_count") ??
      recentEvents.length,
  };
}

export async function getUsageStats(): Promise<UsageStats> {
  const payload = await requestWithFallback<unknown>([
    { path: "/api/v1/usage" },
  ]);
  return normalizeUsageStats(payload);
}

export async function shutdownApp(): Promise<void> {
  await requestJson("/shutdown", "POST");
}

export async function getDatabaseSettings(): Promise<DatabaseSettings> {
  const payload = (await requestJson("/api/v1/settings/database", "GET")) as DatabaseSettings;
  return payload;
}

export async function saveDatabaseSettings(settings: {
  databaseUrl: string;
  vectorDbUrl: string;
}): Promise<{ ok: boolean; message: string }> {
  const payload = (await requestJson("/api/v1/settings/database", "POST", settings)) as {
    ok: boolean;
    message: string;
  };
  return payload;
}

export async function testDatabaseConnection(
  databaseUrl: string,
): Promise<{ ok: boolean; message: string }> {
  const payload = (await requestJson("/api/v1/settings/database/test", "POST", { databaseUrl })) as {
    ok: boolean;
    message: string;
  };
  return payload;
}

async function assembleBootstrapFromIndividualEndpoints(): Promise<BootstrapPayload> {
  const [
    providersResult,
    agentsResult,
    invocationsResult,
    catalogResult,
    templatesResult,
  ] = await Promise.allSettled([
    listProvidersInternal(),
    listAgentsInternal(),
    listInvocationsInternal(),
    listProviderCatalogInternal(),
    listAgentTemplatesInternal(),
  ]);

  const providers = providersResult.status === "fulfilled" ? providersResult.value : [];
  const agents = agentsResult.status === "fulfilled" ? agentsResult.value : [];
  const invocations = invocationsResult.status === "fulfilled" ? invocationsResult.value : [];
  const providerCatalog =
    catalogResult.status === "fulfilled" && catalogResult.value.length > 0
      ? catalogResult.value
      : DEFAULT_PROVIDER_CATALOG;
  const agentTemplates = templatesResult.status === "fulfilled" ? templatesResult.value : [];

  const apiAvailable = [
    providersResult, agentsResult, invocationsResult, catalogResult, templatesResult,
  ].some((result) => result.status === "fulfilled");

  return {
    providers,
    agents,
    invocations,
    providerCatalog,
    agentTemplates,
    apiAvailable,
    source: apiAvailable ? "assembled" : "fallback",
    warning: apiAvailable
      ? null
      : "This Control Plane build does not expose the /api/v1 configuration endpoints yet. System status is available, but provider, agent, and playground actions will remain read-only until those routes are added.",
  };
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}
