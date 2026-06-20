import { useCallback, useEffect, useMemo, useState } from "react";
import { DashboardView } from "./views/DashboardView";
import { ProvidersView } from "./views/ProvidersView";
import { AgentsView } from "./views/AgentsView";
import { PlaygroundView } from "./views/PlaygroundView";
import { SetupView } from "./views/SetupView";
import { SystemView } from "./views/SystemView";
import { WorkloadsView } from "./views/WorkloadsView";
import {
  DEFAULT_PROVIDER_CATALOG,
  getBootstrap,
  getErrorMessage,
  getSystemSnapshot,
  sortAgents,
  sortInvocations,
  sortProviders,
  type AgentConfig,
  type BootstrapPayload,
  type InvocationRecord,
  type ProviderConfig,
  type SystemSnapshot,
} from "./lib/api";
import {
  InlineNotice,
  StatusBadge,
  cx,
  formatRelativeTime,
} from "./components/ui";

type AppView =
  | "dashboard"
  | "providers"
  | "agents"
  | "playground"
  | "setup"
  | "system"
  | "workloads";

const EMPTY_BOOTSTRAP: BootstrapPayload = {
  providers: [],
  agents: [],
  invocations: [],
  providerCatalog: DEFAULT_PROVIDER_CATALOG,
  agentTemplates: [],
  apiAvailable: false,
  source: "fallback",
  warning: null,
};

export default function App() {
  const [activeView, setActiveView] = useState<AppView>("dashboard");
  const [bootstrap, setBootstrap] = useState<BootstrapPayload>(EMPTY_BOOTSTRAP);
  const [system, setSystem] = useState<SystemSnapshot | null>(null);
  const [bootstrapLoading, setBootstrapLoading] = useState(true);
  const [systemLoading, setSystemLoading] = useState(true);
  const [bootstrapError, setBootstrapError] = useState<string | null>(null);
  const [systemError, setSystemError] = useState<string | null>(null);
  const [lastRefreshAt, setLastRefreshAt] = useState<number | null>(null);
  const [selectedPlaygroundAgentId, setSelectedPlaygroundAgentId] = useState<
    string | null
  >(null);

  const refreshBootstrap = useCallback(async (silent = false) => {
    if (!silent) {
      setBootstrapLoading(true);
    }
    try {
      const nextBootstrap = await getBootstrap();
      setBootstrap(nextBootstrap);
      setBootstrapError(null);
      setLastRefreshAt(Date.now());
    } catch (error) {
      setBootstrapError(getErrorMessage(error));
    } finally {
      if (!silent) {
        setBootstrapLoading(false);
      }
    }
  }, []);

  const refreshSystem = useCallback(async (silent = false) => {
    if (!silent) {
      setSystemLoading(true);
    }
    try {
      const nextSystem = await getSystemSnapshot();
      setSystem(nextSystem);
      setSystemError(null);
      setLastRefreshAt(Date.now());
    } catch (error) {
      setSystemError(getErrorMessage(error));
    } finally {
      if (!silent) {
        setSystemLoading(false);
      }
    }
  }, []);

  const refreshAll = useCallback(async () => {
    await Promise.all([refreshBootstrap(false), refreshSystem(false)]);
  }, [refreshBootstrap, refreshSystem]);

  useEffect(() => {
    void refreshAll();
  }, [refreshAll]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void refreshSystem(true);
    }, 4000);
    return () => {
      window.clearInterval(timer);
    };
  }, [refreshSystem]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void refreshBootstrap(true);
    }, 12000);
    return () => {
      window.clearInterval(timer);
    };
  }, [refreshBootstrap]);

  useEffect(() => {
    if (bootstrap.agents.length === 0) {
      setSelectedPlaygroundAgentId(null);
      return;
    }
    if (
      !selectedPlaygroundAgentId ||
      !bootstrap.agents.some((agent) => agent.id === selectedPlaygroundAgentId)
    ) {
      setSelectedPlaygroundAgentId(bootstrap.agents[0].id);
    }
  }, [bootstrap.agents, selectedPlaygroundAgentId]);

  const navItems = useMemo(
    () => [
      {
        id: "dashboard" as const,
        label: "Dashboard",
        description: "Overview and next steps",
        count: null,
      },
      {
        id: "providers" as const,
        label: "Providers",
        description: "Model backends and secrets",
        count: bootstrap.providers.length,
      },
      {
        id: "agents" as const,
        label: "Agents",
        description: "Prompted workflows and schemas",
        count: bootstrap.agents.length,
      },
      {
        id: "playground" as const,
        label: "Playground",
        description: "Run and inspect invocations",
        count: bootstrap.invocations.length,
      },
      {
        id: "setup" as const,
        label: "Setup",
        description: "Dependencies and install guides",
        count:
          system?.dependencies?.dependencies?.filter(
            (d) =>
              d.state !== "DEPENDENCY_STATE_READY" &&
              d.state !== "DEPENDENCY_STATE_DISABLED",
          ).length ?? null,
      },
      {
        id: "system" as const,
        label: "System",
        description: "Health, session, and events",
        count: system?.eventCount ?? null,
      },
      {
        id: "workloads" as const,
        label: "Workloads",
        description: "Docker containers and previews",
        count: null,
      },
    ],
    [
      bootstrap.agents.length,
      bootstrap.invocations.length,
      bootstrap.providers.length,
      system?.eventCount,
      system?.dependencies,
    ],
  );

  const handleProviderSaved = useCallback((provider: ProviderConfig) => {
    setBootstrap((current) => ({
      ...current,
      providers: sortProviders(upsertById(current.providers, provider)),
    }));
  }, []);

  const handleProviderDeleted = useCallback((providerId: string) => {
    setBootstrap((current) => ({
      ...current,
      providers: current.providers.filter(
        (provider) => provider.id !== providerId,
      ),
    }));
  }, []);

  const handleAgentSaved = useCallback((agent: AgentConfig) => {
    setBootstrap((current) => ({
      ...current,
      agents: sortAgents(upsertById(current.agents, agent)),
    }));
  }, []);

  const handleAgentDeleted = useCallback((agentId: string) => {
    setBootstrap((current) => ({
      ...current,
      agents: current.agents.filter((agent) => agent.id !== agentId),
    }));
  }, []);

  const handleInvocationSaved = useCallback((invocation: InvocationRecord) => {
    setBootstrap((current) => ({
      ...current,
      invocations: sortInvocations(
        upsertById(current.invocations, invocation),
      ).slice(0, 50),
    }));
  }, []);

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div className="brand-block">
          <div className="brand-mark">VL</div>
          <div>
            <strong>VLoop</strong>
            <p>Python Control Plane shell</p>
          </div>
        </div>

        <nav className="nav-list" aria-label="Primary">
          {navItems.map((item) => (
            <button
              key={item.id}
              type="button"
              className={cx("nav-item", activeView === item.id && "is-active")}
              onClick={() => setActiveView(item.id)}
            >
              <div>
                <strong>{item.label}</strong>
                <span>{item.description}</span>
              </div>
              {item.count !== null ? (
                <span className="nav-item__count">{item.count}</span>
              ) : null}
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <StatusBadge
            status={
              system?.health.status ?? (systemLoading ? "starting" : "unknown")
            }
            label={
              system?.health.status
                ? undefined
                : systemLoading
                  ? "Loading"
                  : "Unknown"
            }
          />
          <StatusBadge
            tone={bootstrap.apiAvailable ? "accent" : "neutral"}
            label={
              bootstrap.apiAvailable
                ? "Config API ready"
                : "System endpoints only"
            }
          />
          <p>
            {lastRefreshAt
              ? `Refreshed ${formatRelativeTime(lastRefreshAt)}`
              : "Waiting for first refresh"}
          </p>
        </div>
      </aside>

      <div className="app-main">
        <header className="app-toolbar">
          <div className="app-toolbar__summary">
            <h1>VLoop Control Plane</h1>
            <p>
              Restrained, local-first tooling for provider setup, agent
              authoring, live runs, and Control Plane diagnostics.
            </p>
          </div>
          <div className="app-toolbar__actions">
            <StatusBadge
              status={
                system?.health.status ??
                (systemLoading ? "starting" : "unknown")
              }
            />
            <button
              className="button button--secondary"
              type="button"
              onClick={() => {
                void refreshAll();
              }}
              disabled={bootstrapLoading || systemLoading}
            >
              {bootstrapLoading || systemLoading ? "Refreshing…" : "Refresh"}
            </button>
          </div>
        </header>

        <main className="app-content">
          {bootstrapError ? (
            <InlineNotice
              tone="bad"
              title="Could not refresh configuration data"
            >
              <p>{bootstrapError}</p>
            </InlineNotice>
          ) : null}

          {renderActiveView({
            activeView,
            bootstrap,
            system,
            systemError,
            onNavigate: setActiveView,
            selectedPlaygroundAgentId,
            onSelectPlaygroundAgent: setSelectedPlaygroundAgentId,
            onProviderSaved: handleProviderSaved,
            onProviderDeleted: handleProviderDeleted,
            onAgentSaved: handleAgentSaved,
            onAgentDeleted: handleAgentDeleted,
            onInvocationSaved: handleInvocationSaved,
          })}
        </main>
      </div>
    </div>
  );
}

function renderActiveView(args: {
  activeView: AppView;
  bootstrap: BootstrapPayload;
  system: SystemSnapshot | null;
  systemError: string | null;
  onNavigate: (view: AppView) => void;
  selectedPlaygroundAgentId: string | null;
  onSelectPlaygroundAgent: (agentId: string) => void;
  onProviderSaved: (provider: ProviderConfig) => void;
  onProviderDeleted: (providerId: string) => void;
  onAgentSaved: (agent: AgentConfig) => void;
  onAgentDeleted: (agentId: string) => void;
  onInvocationSaved: (invocation: InvocationRecord) => void;
}) {
  const {
    activeView,
    bootstrap,
    system,
    systemError,
    onNavigate,
    selectedPlaygroundAgentId,
    onSelectPlaygroundAgent,
    onProviderSaved,
    onProviderDeleted,
    onAgentSaved,
    onAgentDeleted,
    onInvocationSaved,
  } = args;

  switch (activeView) {
    case "providers":
      return (
        <ProvidersView
          providers={bootstrap.providers}
          providerCatalog={bootstrap.providerCatalog}
          apiAvailable={bootstrap.apiAvailable}
          warning={bootstrap.warning}
          onProviderSaved={onProviderSaved}
          onProviderDeleted={onProviderDeleted}
        />
      );
    case "agents":
      return (
        <AgentsView
          agents={bootstrap.agents}
          providers={bootstrap.providers}
          agentTemplates={bootstrap.agentTemplates}
          apiAvailable={bootstrap.apiAvailable}
          warning={bootstrap.warning}
          onAgentSaved={onAgentSaved}
          onAgentDeleted={onAgentDeleted}
          onOpenPlayground={(agentId) => {
            onSelectPlaygroundAgent(agentId);
            onNavigate("playground");
          }}
        />
      );
    case "playground":
      return (
        <PlaygroundView
          agents={bootstrap.agents}
          providers={bootstrap.providers}
          invocations={bootstrap.invocations}
          apiAvailable={bootstrap.apiAvailable}
          warning={bootstrap.warning}
          selectedAgentId={selectedPlaygroundAgentId}
          onSelectAgent={onSelectPlaygroundAgent}
          onInvocationSaved={onInvocationSaved}
        />
      );
    case "system":
      return (
        <SystemView
          system={system}
          systemError={systemError}
          warning={bootstrap.warning}
        />
      );
    case "workloads":
      return <WorkloadsView />;
    case "setup":
      return <SetupView system={system} systemError={systemError} />;
    case "dashboard":
    default:
      return (
        <DashboardView
          providers={bootstrap.providers}
          agents={bootstrap.agents}
          invocations={bootstrap.invocations}
          health={system?.health ?? null}
          session={system?.session ?? null}
          windowState={system?.window ?? null}
          recentEvents={system?.recentEvents ?? []}
          apiAvailable={bootstrap.apiAvailable}
          warning={bootstrap.warning}
          onNavigate={onNavigate}
          onSelectPlaygroundAgent={onSelectPlaygroundAgent}
        />
      );
  }
}

function upsertById<T extends { id: string }>(current: T[], nextItem: T): T[] {
  const next = current.filter((item) => item.id !== nextItem.id);
  next.unshift(nextItem);
  return next;
}
