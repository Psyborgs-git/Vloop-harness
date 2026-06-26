import type { InvocationRecord, ProviderConfig } from "../../lib/api";
import {
  EmptyState,
  StatusBadge,
  formatRelativeTime,
} from "../../components/ui";

interface RecentRunsProps {
  invocations: InvocationRecord[];
  selectedInvocationId: string | null;
  providerMap: Map<string, ProviderConfig>;
  onSelect: (invocation: InvocationRecord) => void;
}

export function RecentRuns({
  invocations,
  selectedInvocationId,
  providerMap,
  onSelect,
}: RecentRunsProps) {
  if (invocations.length === 0) {
    return (
      <EmptyState
        title="No recent runs for this agent"
        description="Start the first invocation to see status history, timings, provider resolution, and output previews here."
      />
    );
  }

  return (
    <div className="stack-list">
      {invocations.map((invocation) => (
        <button
          key={invocation.id}
          type="button"
          className={
            selectedInvocationId === invocation.id
              ? "list-action list-action--active"
              : "list-action"
          }
          onClick={() => onSelect(invocation)}
        >
          <div>
            <div className="list-action__title-row">
              <strong>
                {providerMap.get(invocation.providerId)?.name ??
                  invocation.providerId}
              </strong>
              <StatusBadge status={invocation.status} />
            </div>
            <p>{invocation.resolvedModel ?? "Model pending"}</p>
          </div>
          <span className="list-action__meta">
            {formatRelativeTime(
              invocation.finishedAt ??
                invocation.startedAt ??
                invocation.createdAt,
            )}
          </span>
        </button>
      ))}
    </div>
  );
}
