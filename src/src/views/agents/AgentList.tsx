import type { AgentConfig, ProviderConfig } from "../../lib/api";
import { EmptyState, StatusBadge, cx } from "../../components/ui";

interface AgentListProps {
  agents: AgentConfig[];
  providers: ProviderConfig[];
  selectedId: string | "new" | null;
  onSelect: (agent: AgentConfig) => void;
  onStartNew: () => void;
}

export function AgentList({
  agents,
  providers,
  selectedId,
  onSelect,
  onStartNew,
}: AgentListProps) {
  const providerMap = new Map(providers.map((p) => [p.id, p]));

  if (agents.length === 0) {
    return (
      <EmptyState
        title="No agents saved"
        description="Start from a template or build one from scratch once a provider exists."
        action={
          <button
            className="button button--primary"
            type="button"
            onClick={onStartNew}
          >
            Create agent
          </button>
        }
      />
    );
  }

  return (
    <div className="stack-list">
      {agents.map((agent) => {
        const provider = providerMap.get(agent.defaultProviderId);
        return (
          <button
            key={agent.id}
            type="button"
            className={cx(
              "resource-row",
              selectedId === agent.id && "is-active",
            )}
            onClick={() => onSelect(agent)}
          >
            <div className="resource-row__header">
              <strong>{agent.name}</strong>
              <StatusBadge
                status={agent.enabled ? "enabled" : "disabled"}
                label={agent.enabled ? "Enabled" : "Disabled"}
              />
            </div>
            <p>
              {agent.outputMode.toUpperCase()} ·{" "}
              {provider?.name ?? "Missing provider"}
            </p>
            <div className="resource-row__meta-row">
              <StatusBadge
                status={agent.reasoningMode}
                label={
                  agent.reasoningMode === "chain_of_thought"
                    ? "Chain of thought"
                    : "Predict"
                }
                tone="accent"
              />
              <span className="muted-text">
                {agent.inputFields.length} input field
                {agent.inputFields.length === 1 ? "" : "s"}
              </span>
            </div>
          </button>
        );
      })}
    </div>
  );
}
