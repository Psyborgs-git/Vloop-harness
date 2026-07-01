import { useEffect, useState } from "react";
import { Sidebar } from "./components/Sidebar";
import { Toolbar } from "./components/Toolbar";
import { useAppData } from "./hooks/useAppData";
import { InlineNotice } from "./components/ui";
import { ChatView } from "./views/ChatView";
import { DashboardView } from "./views/DashboardView";
import { ProvidersView } from "./views/providers/ProvidersView";
import { AgentsView } from "./views/agents/AgentsView";
import { PlaygroundView } from "./views/playground/PlaygroundView";
import { SettingsView } from "./views/SettingsView";
import { SetupView } from "./views/SetupView";
import { SystemView } from "./views/SystemView";
import { WorkloadsView } from "./views/WorkloadsView";
import { WorkflowsView } from "./views/workflows/WorkflowsView";
import { ApprovalsView } from "./views/approvals/ApprovalsView";
import { BudgetsView } from "./views/budgets/BudgetsView";
import { CheckpointsView } from "./views/checkpoints/CheckpointsView";
import { ScheduleView } from "./views/schedule/ScheduleView";
import { UsageView } from "./views/UsageView";
import type { AgentConfig, InvocationRecord, ProviderConfig } from "./lib/api";

export type AppView =
  | "dashboard"
  | "providers"
  | "agents"
  | "chat"
  | "playground"
  | "settings"
  | "setup"
  | "system"
  | "workloads"
  | "workflows"
  | "approvals"
  | "budgets"
  | "checkpoints"
  | "schedule"
  | "usage";

export default function App() {
  const {
    bootstrap,
    system,
    bootstrapLoading,
    systemLoading,
    bootstrapError,
    theme,
    setTheme,
    sidebarCollapsed,
    toggleSidebar,
    shuttingDown,
    shutdownError,
    lastRefreshAt,
    handleQuit,
    refreshAll,
    handleProviderSaved,
    handleProviderDeleted,
    handleAgentSaved,
    handleAgentDeleted,
    handleInvocationSaved,
  } = useAppData();

  const [activeView, setActiveView] = useState<AppView>("dashboard");
  const [selectedPlaygroundAgentId, setSelectedPlaygroundAgentId] = useState<
    string | null
  >(null);

  // Auto-select first agent for playground
  useEffect(() => {
    if (bootstrap.agents.length === 0) {
      setSelectedPlaygroundAgentId(null);
      return;
    }
    if (
      !selectedPlaygroundAgentId ||
      !bootstrap.agents.some((a) => a.id === selectedPlaygroundAgentId)
    ) {
      setSelectedPlaygroundAgentId(bootstrap.agents[0].id);
    }
  }, [bootstrap.agents, selectedPlaygroundAgentId]);

  return (
    <div
      className={
        sidebarCollapsed
          ? "app-shell app-shell--sidebar-collapsed"
          : "app-shell"
      }
    >
      <Sidebar
        activeView={activeView}
        onNavigate={setActiveView}
        bootstrap={bootstrap}
        system={system}
        systemLoading={systemLoading}
        lastRefreshAt={lastRefreshAt}
        collapsed={sidebarCollapsed}
        onToggleCollapse={toggleSidebar}
        theme={theme}
        onSetTheme={setTheme}
        shuttingDown={shuttingDown}
        shutdownError={shutdownError}
        onQuit={() => void handleQuit()}
      />

      <div className="app-main">
        <Toolbar
          system={system}
          systemLoading={systemLoading}
          bootstrapLoading={bootstrapLoading}
          onRefresh={refreshAll}
        />

        <main className="app-content">
          {bootstrapError ? (
            <InlineNotice
              tone="bad"
              title="Could not refresh configuration data"
            >
              <p>{bootstrapError}</p>
            </InlineNotice>
          ) : null}

          <ActiveView
            view={activeView}
            bootstrap={bootstrap}
            system={system}
            onNavigate={setActiveView}
            selectedAgentId={selectedPlaygroundAgentId}
            onSelectAgent={setSelectedPlaygroundAgentId}
            onProviderSaved={handleProviderSaved}
            onProviderDeleted={handleProviderDeleted}
            onAgentSaved={handleAgentSaved}
            onAgentDeleted={handleAgentDeleted}
            onInvocationSaved={handleInvocationSaved}
          />
        </main>
      </div>
    </div>
  );
}

/* ─────── Active View Router ─────── */

interface ActiveViewProps {
  view: AppView;
  bootstrap: ReturnType<typeof useAppData>["bootstrap"];
  system: ReturnType<typeof useAppData>["system"];
  onNavigate: (v: AppView) => void;
  selectedAgentId: string | null;
  onSelectAgent: (id: string) => void;
  onProviderSaved: (p: ProviderConfig) => void;
  onProviderDeleted: (id: string) => void;
  onAgentSaved: (a: AgentConfig) => void;
  onAgentDeleted: (id: string) => void;
  onInvocationSaved: (i: InvocationRecord) => void;
}

function ActiveView({
  view,
  bootstrap,
  system,
  onNavigate,
  selectedAgentId,
  onSelectAgent,
  onProviderSaved,
  onProviderDeleted,
  onAgentSaved,
  onAgentDeleted,
  onInvocationSaved,
}: ActiveViewProps) {
  switch (view) {
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
            onSelectAgent(agentId);
            onNavigate("playground");
          }}
        />
      );
    case "chat":
      return (
        <ChatView
          agents={bootstrap.agents}
          providers={bootstrap.providers}
          apiAvailable={bootstrap.apiAvailable}
          warning={bootstrap.warning}
        />
      );
    case "usage":
      return <UsageView />;
    case "playground":
      return (
        <PlaygroundView
          agents={bootstrap.agents}
          providers={bootstrap.providers}
          invocations={bootstrap.invocations}
          apiAvailable={bootstrap.apiAvailable}
          warning={bootstrap.warning}
          selectedAgentId={selectedAgentId}
          onSelectAgent={onSelectAgent}
          onInvocationSaved={onInvocationSaved}
        />
      );
    case "system":
      return (
        <SystemView
          system={system}
          systemError={null}
          warning={bootstrap.warning}
        />
      );
    case "workloads":
      return <WorkloadsView />;
    case "workflows":
      return <WorkflowsView />;
    case "approvals":
      return <ApprovalsView />;
    case "budgets":
      return <BudgetsView />;
    case "checkpoints":
      return <CheckpointsView />;
    case "schedule":
      return <ScheduleView />;
    case "setup":
      return <SetupView system={system} systemError={null} />;
    case "settings":
      return <SettingsView apiAvailable={bootstrap.apiAvailable} />;
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
          onSelectPlaygroundAgent={onSelectAgent}
        />
      );
  }
}
