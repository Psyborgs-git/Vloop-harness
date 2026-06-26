import type { SystemSnapshot } from "../lib/api";
import { StatusBadge } from "./ui";

interface ToolbarProps {
  system: SystemSnapshot | null;
  systemLoading: boolean;
  bootstrapLoading: boolean;
  onRefresh: () => void;
}

export function Toolbar({
  system,
  systemLoading,
  bootstrapLoading,
  onRefresh,
}: ToolbarProps) {
  const loading = bootstrapLoading || systemLoading;

  return (
    <header className="app-toolbar">
      <div className="app-toolbar__summary">
        <h1>VLoop Control Plane</h1>
        <p>
          Restrained, local-first tooling for provider setup, agent authoring,
          live runs, and Control Plane diagnostics.
        </p>
      </div>
      <div className="app-toolbar__actions">
        <StatusBadge
          status={system?.health.status ?? (systemLoading ? "starting" : "unknown")}
        />
        <button
          className="button button--secondary"
          type="button"
          onClick={onRefresh}
          disabled={loading}
        >
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>
    </header>
  );
}
