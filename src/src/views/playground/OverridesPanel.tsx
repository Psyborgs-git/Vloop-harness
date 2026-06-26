import type { AgentConfig, ProviderConfig } from "../../lib/api";

export interface PlaygroundOverridesState {
  providerId: string;
  model: string;
  temperature: string;
  maxTokens: string;
}

interface OverridesPanelProps {
  agent: AgentConfig;
  providers: ProviderConfig[];
  overrides: PlaygroundOverridesState;
  selectedProvider: ProviderConfig | undefined;
  onChangeOverrides: <K extends keyof PlaygroundOverridesState>(
    key: K,
    value: PlaygroundOverridesState[K],
  ) => void;
}

export function OverridesPanel({
  agent,
  providers,
  overrides,
  selectedProvider,
  onChangeOverrides,
}: OverridesPanelProps) {
  return (
    <details className="details-block">
      <summary>Advanced overrides</summary>
      <div className="form-grid form-grid--two">
        <label className="field">
          <span className="field__label">Provider override</span>
          <select
            className="select"
            value={overrides.providerId || agent.defaultProviderId}
            onChange={(event) =>
              onChangeOverrides("providerId", event.target.value)
            }
          >
            {providers.map((provider) => (
              <option key={provider.id} value={provider.id}>
                {provider.name}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span className="field__label">Model override</span>
          <input
            className="input mono"
            type="text"
            value={overrides.model}
            onChange={(event) => onChangeOverrides("model", event.target.value)}
            placeholder={selectedProvider?.defaultModel ?? "Optional"}
          />
        </label>
      </div>
      <div className="form-grid form-grid--two">
        <label className="field">
          <span className="field__label">Temperature override</span>
          <input
            className="input mono"
            type="number"
            min="0"
            step="0.1"
            value={overrides.temperature}
            onChange={(event) =>
              onChangeOverrides("temperature", event.target.value)
            }
            placeholder={String(agent.temperature)}
          />
        </label>
        <label className="field">
          <span className="field__label">Max tokens override</span>
          <input
            className="input mono"
            type="number"
            min="32"
            step="1"
            value={overrides.maxTokens}
            onChange={(event) =>
              onChangeOverrides("maxTokens", event.target.value)
            }
            placeholder={String(agent.maxTokens)}
          />
        </label>
      </div>
    </details>
  );
}
