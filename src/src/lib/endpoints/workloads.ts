import type { WorkloadRecord, WorkloadLogsResponse } from "../types";
import { requestJson } from "../api-client";
import { normalizeWorkloadRecord } from "../normalizers";
import { normalizeStringArray } from "../api-client";

export async function listWorkloads(): Promise<WorkloadRecord[]> {
  const payload = (await requestJson("/api/v1/workloads", "GET")) as {
    workloads: unknown;
  };
  return normalizeStringArray(payload.workloads).map(normalizeWorkloadRecord);
}

export async function createWorkload(spec: {
  image: string;
  command?: string[];
  ports?: number[];
  environment?: Record<string, string>;
  class?: string;
}): Promise<WorkloadRecord> {
  const payload = (await requestJson("/api/v1/workloads", "POST", {
    image: spec.image,
    command: spec.command ?? [],
    ports: spec.ports ?? [],
    environment: spec.environment ?? {},
    class: spec.class ?? "HARNESS",
  })) as { workload: unknown };
  return normalizeWorkloadRecord(payload.workload);
}

export async function startWorkload(workloadId: string): Promise<WorkloadRecord> {
  const payload = (await requestJson(
    `/api/v1/workloads/${encodeURIComponent(workloadId)}/start`,
    "POST",
  )) as { workload: unknown };
  return normalizeWorkloadRecord(payload.workload);
}

export async function stopWorkload(workloadId: string): Promise<WorkloadRecord> {
  const payload = (await requestJson(
    `/api/v1/workloads/${encodeURIComponent(workloadId)}/stop`,
    "POST",
  )) as { workload: unknown };
  return normalizeWorkloadRecord(payload.workload);
}

export async function getWorkloadLogs(workloadId: string): Promise<WorkloadLogsResponse> {
  const payload = (await requestJson(
    `/api/v1/workloads/${encodeURIComponent(workloadId)}/logs`,
    "GET",
  )) as WorkloadLogsResponse;
  return payload;
}
