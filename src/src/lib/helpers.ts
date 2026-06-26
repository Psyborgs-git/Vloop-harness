import type { AgentConfig, InvocationRecord, KernelEventRecord, ProviderConfig } from "./types";

export function sortProviders(providers: ProviderConfig[]): ProviderConfig[] {
  return [...providers].sort((left, right) => {
    const delta =
      toSortableTimestamp(right.updatedAt) -
      toSortableTimestamp(left.updatedAt);
    if (delta !== 0) {
      return delta;
    }
    return left.name.localeCompare(right.name);
  });
}

export function sortAgents(agents: AgentConfig[]): AgentConfig[] {
  return [...agents].sort((left, right) => {
    const delta =
      toSortableTimestamp(right.updatedAt) -
      toSortableTimestamp(left.updatedAt);
    if (delta !== 0) {
      return delta;
    }
    return left.name.localeCompare(right.name);
  });
}

export function sortInvocations(
  invocations: InvocationRecord[],
): InvocationRecord[] {
  return [...invocations].sort((left, right) => {
    const delta =
      toSortableTimestamp(right.createdAt) -
      toSortableTimestamp(left.createdAt);
    if (delta !== 0) {
      return delta;
    }
    return right.id.localeCompare(left.id);
  });
}

export function sortKernelEvents(
  events: KernelEventRecord[],
): KernelEventRecord[] {
  return [...events].sort(
    (left, right) => right.timestampUnixMs - left.timestampUnixMs,
  );
}

export function isTerminalInvocationStatus(
  status: string | null | undefined,
): boolean {
  return (
    status === "succeeded" || status === "failed" || status === "cancelled"
  );
}

export function toSortableTimestamp(
  value: string | number | null | undefined,
): number {
  if (typeof value === "number") {
    return value;
  }
  if (!value) {
    return 0;
  }
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
}

export function humanizeIdentifier(value: string): string | null {
  if (!value) {
    return null;
  }
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(
      /(^|\s)(\w)/g,
      (_: string, prefix: string, char: string) => `${prefix}${char.toUpperCase()}`,
    );
}
