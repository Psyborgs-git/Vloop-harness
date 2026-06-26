import type { ProviderConfig } from "../../lib/api";
import { EmptyState, StatusBadge, cx } from "../../components/ui";

interface ProviderListProps {
  providers: ProviderConfig[];
  selectedId: string | "new" | null;
  onSelect: (provider: ProviderConfig) => void;
  onStartNew: () => void;
}

export function ProviderList({
  providers,
  selectedId,
  onSelect,
  onStartNew,
}: ProviderListProps) {
  if (providers.length === 0) {
    return (
      <EmptyState
        title="No providers configured"
        description="Start with the mock provider for a safe local loop, or add a real backend like Ollama, OpenAI, Anthropic, OpenRouter, or Azure OpenAI."
        action={
          <button
            className="button button--primary"
            type="button"
            onClick={onStartNew}
          >
            Create provider
          </button>
        }
      />
    );
  }

  return (
    <div className="stack-list">
      {providers.map((provider) => (
        <button
          key={provider.id}
          type="button"
          className={cx(
            "resource-row",
            selectedId === provider.id && "is-active",
          )}
          onClick={() => onSelect(provider)}
        >
          <div className="resource-row__header">
            <strong>{provider.name}</strong>
            <StatusBadge
              status={provider.lastTestStatus}
              label={
                provider.lastTestStatus === "unknown" ? "Untested" : undefined
              }
            />
          </div>
          <p>
            {provider.providerType} · {provider.defaultModel}
          </p>
          <div className="resource-row__meta-row">
            <StatusBadge
              status={provider.enabled ? "enabled" : "disabled"}
              label={provider.enabled ? "Enabled" : "Disabled"}
            />
            <StatusBadge
              status={provider.hasSecret ? "ready" : "pending"}
              label={provider.hasSecret ? "Secret ready" : "Secret missing"}
              tone={provider.hasSecret ? "good" : "warn"}
            />
          </div>
        </button>
      ))}
    </div>
  );
}
