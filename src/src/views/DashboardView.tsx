import type {
  AgentConfig,
  HealthSnapshot,
  InvocationRecord,
  KernelEventRecord,
  ProviderConfig,
  SessionSnapshot,
  WindowSnapshot,
} from "../lib/api";
import {
  EmptyState,
  InlineNotice,
  KeyValueList,
  PageHeader,
  Panel,
  StatusBadge,
  formatDateTime,
  formatDuration,
  formatRelativeTime,
} from "../components/ui";

interface DashboardViewProps {
  providers: ProviderConfig[];
  agents: AgentConfig[];
  invocations: InvocationRecord[];
  health: HealthSnapshot | null;
  session: SessionSnapshot | null;
  windowState: WindowSnapshot | null;
  recentEvents: KernelEventRecord[];
  apiAvailable: boolean;
  warning: string | null;
  onNavigate: (
    section: "dashboard" | "providers" | "agents" | "playground" | "system",
  ) => void;
  onSelectPlaygroundAgent: (agentId: string) => void;
}

export function DashboardView({
  providers,
  agents,
  invocations,
  health,
  session,
  windowState,
  recentEvents,
  apiAvailable,
  warning,
  onNavigate,
  onSelectPlaygroundAgent,
}: DashboardViewProps) {
  const providerMap = new Map(
    providers.map((provider) => [provider.id, provider]),
  );
  const agentMap = new Map(agents.map((agent) => [agent.id, agent]));

  const enabledProviders = providers.filter(
    (provider) => provider.enabled,
  ).length;
  const readyProviders = providers.filter(
    (provider) =>
      provider.enabled &&
      provider.hasSecret &&
      provider.lastTestStatus === "ok",
  ).length;
  const enabledAgents = agents.filter((agent) => agent.enabled).length;
  const successfulRuns = invocations.filter(
    (invocation) => invocation.status === "succeeded",
  ).length;
  const blockedProviders = providers.filter(
    (provider) =>
      provider.enabled &&
      (!provider.hasSecret || provider.lastTestStatus === "error"),
  );
  const latestRun = invocations[0] ?? null;
  const latestEvent = recentEvents[0] ?? null;

  const nextSteps: Array<{
    label: string;
    description: string;
    onClick: () => void;
  }> = [];

  if (providers.length === 0) {
    nextSteps.push({
      label: "Create the first provider",
      description:
        "Add a mock or real model backend so agents can resolve a default provider.",
      onClick: () => onNavigate("providers"),
    });
  }
  if (blockedProviders.length > 0) {
    nextSteps.push({
      label: "Fix provider secrets or tests",
      description:
        "At least one enabled provider still needs a secret or a passing connectivity test.",
      onClick: () => onNavigate("providers"),
    });
  }
  if (providers.length > 0 && agents.length === 0) {
    nextSteps.push({
      label: "Create the first agent",
      description:
        "Define instructions, inputs, output mode, and a default provider before using the playground.",
      onClick: () => onNavigate("agents"),
    });
  }
  if (agents.length > 0 && invocations.length === 0) {
    nextSteps.push({
      label: "Run an agent in the playground",
      description:
        "Exercise the form-generated inputs, inspect the invocation timeline, and verify outputs end to end.",
      onClick: () => onNavigate("playground"),
    });
  }

  return (
    <div className="page-stack">
      <PageHeader
        title="Dashboard"
        description="Track Control Plane readiness, provider health, recent agent activity, and the next setup step from one place."
        actions={
          <div className="button-row">
            <button
              className="button button--secondary"
              type="button"
              onClick={() => onNavigate("providers")}
            >
              Manage providers
            </button>
            <button
              className="button button--secondary"
              type="button"
              onClick={() => onNavigate("agents")}
            >
              Manage agents
            </button>
            <button
              className="button button--primary"
              type="button"
              onClick={() => onNavigate("playground")}
            >
              Open playground
            </button>
          </div>
        }
      />

      {warning ? (
        <InlineNotice
          tone={apiAvailable ? "warn" : "bad"}
          title={
            apiAvailable
              ? "Bootstrap endpoint unavailable"
              : "Configuration API unavailable"
          }
        >
          <p>{warning}</p>
        </InlineNotice>
      ) : null}

      <div className="overview-grid">
        <Panel
          title="Control Plane"
          subtitle="Shell and kernel registration status at a glance."
        >
          <div className="metric-stack">
            <div className="metric-row">
              <span className="metric-label">Runtime status</span>
              <StatusBadge status={health?.status ?? "unknown"} />
            </div>
            <div className="metric-row">
              <span className="metric-label">Session</span>
              <span className="metric-value mono">
                {health?.sessionId ?? "Not registered yet"}
              </span>
            </div>
            <div className="metric-row">
              <span className="metric-label">Window</span>
              <StatusBadge
                status={windowState?.isOpen ? "ready" : "hidden"}
                label={windowState?.isOpen ? "Open" : "Hidden"}
              />
            </div>
            <div className="metric-row">
              <span className="metric-label">Last event</span>
              <span className="metric-value">
                {latestEvent
                  ? `${latestEvent.eventType} · ${formatRelativeTime(
                      latestEvent.timestampUnixMs,
                    )}`
                  : "No kernel events yet"}
              </span>
            </div>
          </div>
        </Panel>

        <Panel
          title="Providers"
          subtitle="Model backends, secrets, and test coverage."
        >
          <div className="metric-grid metric-grid--compact">
            <div className="metric-card">
              <strong>{providers.length}</strong>
              <span>Total providers</span>
            </div>
            <div className="metric-card">
              <strong>{enabledProviders}</strong>
              <span>Enabled</span>
            </div>
            <div className="metric-card">
              <strong>{readyProviders}</strong>
              <span>Ready for use</span>
            </div>
          </div>
          <p className="muted-text">
            {blockedProviders.length > 0
              ? `${blockedProviders.length} enabled provider${
                  blockedProviders.length === 1 ? "" : "s"
                } still need a secret or a passing test.`
              : providers.length > 0
                ? "All enabled providers look usable from the current snapshot."
                : "No providers configured yet."}
          </p>
        </Panel>

        <Panel
          title="Agents"
          subtitle="Saved agent definitions and routing defaults."
        >
          <div className="metric-grid metric-grid--compact">
            <div className="metric-card">
              <strong>{agents.length}</strong>
              <span>Total agents</span>
            </div>
            <div className="metric-card">
              <strong>{enabledAgents}</strong>
              <span>Enabled</span>
            </div>
            <div className="metric-card">
              <strong>
                {agents.filter((agent) => agent.outputMode === "json").length}
              </strong>
              <span>JSON agents</span>
            </div>
          </div>
          <p className="muted-text">
            {agents.length > 0
              ? "Use the playground to run an agent with live provider settings and inspect its invocation timeline."
              : "Create at least one agent before using the playground."}
          </p>
        </Panel>

        <Panel
          title="Runs"
          subtitle="Recent invocation activity across all agents."
        >
          <div className="metric-grid metric-grid--compact">
            <div className="metric-card">
              <strong>{invocations.length}</strong>
              <span>Recent runs</span>
            </div>
            <div className="metric-card">
              <strong>{successfulRuns}</strong>
              <span>Succeeded</span>
            </div>
            <div className="metric-card">
              <strong>
                {
                  invocations.filter(
                    (invocation) => invocation.status === "failed",
                  ).length
                }
              </strong>
              <span>Failed</span>
            </div>
          </div>
          <p className="muted-text">
            {latestRun
              ? `Last run ${formatRelativeTime(
                  latestRun.finishedAt ??
                    latestRun.startedAt ??
                    latestRun.createdAt,
                )}`
              : "Run history will appear here after the first playground invocation."}
          </p>
        </Panel>
      </div>

      <div className="page-grid page-grid--sidebar">
        <Panel
          title="Recommended next steps"
          subtitle="The fastest path to a healthy local loop."
        >
          {nextSteps.length > 0 ? (
            <div className="stack-list">
              {nextSteps.slice(0, 3).map((step) => (
                <button
                  className="list-action"
                  type="button"
                  key={step.label}
                  onClick={step.onClick}
                >
                  <div>
                    <strong>{step.label}</strong>
                    <p>{step.description}</p>
                  </div>
                  <span className="list-action__meta">Open</span>
                </button>
              ))}
            </div>
          ) : (
            <EmptyState
              title="Everything needed is in place"
              description="Providers, agents, and recent runs are all present. Use the playground to keep iterating or open System for deeper diagnostics."
              action={
                <button
                  className="button button--primary"
                  type="button"
                  onClick={() => onNavigate("playground")}
                >
                  Continue in playground
                </button>
              }
            />
          )}
        </Panel>

        <Panel
          title="System summary"
          subtitle="Kernel session, shell address, and last heartbeat."
        >
          <KeyValueList
            items={[
              {
                label: "Kernel endpoint",
                value: (
                  <span className="mono break-anywhere">
                    {health?.kernelEndpoint ?? "—"}
                  </span>
                ),
              },
              {
                label: "HTTP shell",
                value: (
                  <span className="mono break-anywhere">
                    {health?.httpBaseUrl ?? "—"}
                  </span>
                ),
              },
              {
                label: "Granted scopes",
                value: session?.grantedScopes.length
                  ? session.grantedScopes.join(", ")
                  : "None granted yet",
              },
              {
                label: "Last heartbeat",
                value: session?.lastHeartbeatAtUnixMs
                  ? formatDateTime(session.lastHeartbeatAtUnixMs)
                  : "—",
              },
              {
                label: "Available runtimes",
                value: session?.activeConfig?.availableRuntimes.length
                  ? session.activeConfig.availableRuntimes.join(", ")
                  : "—",
              },
              {
                label: "Window URL",
                value: (
                  <span className="mono break-anywhere">
                    {windowState?.loadedUrl ?? windowState?.shellUrl ?? "—"}
                  </span>
                ),
              },
            ]}
          />
        </Panel>
      </div>

      <div className="page-grid page-grid--sidebar">
        <Panel
          title="Recent invocations"
          subtitle="Jump straight into the latest run or diagnose a failed response."
        >
          {invocations.length > 0 ? (
            <div className="stack-list">
              {invocations.slice(0, 8).map((invocation) => {
                const agent = agentMap.get(invocation.agentId);
                const provider = providerMap.get(invocation.providerId);
                return (
                  <button
                    className="list-action"
                    type="button"
                    key={invocation.id}
                    onClick={() => {
                      onSelectPlaygroundAgent(invocation.agentId);
                      onNavigate("playground");
                    }}
                  >
                    <div>
                      <div className="list-action__title-row">
                        <strong>{agent?.name ?? "Unknown agent"}</strong>
                        <StatusBadge status={invocation.status} />
                      </div>
                      <p>
                        {provider?.name ?? "Unknown provider"} ·{" "}
                        {invocation.resolvedModel ?? "Model pending"}
                      </p>
                    </div>
                    <span className="list-action__meta">
                      {formatDuration(
                        invocation.startedAt ?? invocation.createdAt,
                        invocation.finishedAt,
                      )}
                    </span>
                  </button>
                );
              })}
            </div>
          ) : (
            <EmptyState
              title="No runs yet"
              description="Run an enabled agent from the playground to populate invocation history, reasoning traces, and output previews."
              action={
                <button
                  className="button button--primary"
                  type="button"
                  onClick={() => onNavigate("playground")}
                >
                  Open playground
                </button>
              }
            />
          )}
        </Panel>

        <Panel
          title="Recent kernel events"
          subtitle="A short feed of Control Plane and kernel activity."
        >
          {recentEvents.length > 0 ? (
            <div className="timeline">
              {recentEvents.slice(0, 6).map((event) => (
                <article
                  className="timeline__item"
                  key={`${event.eventId}-${event.timestampUnixMs}`}
                >
                  <div className="timeline__title-row">
                    <strong>{event.eventType}</strong>
                    <StatusBadge status={event.status} />
                  </div>
                  <p>
                    {event.message ||
                      `${event.resourceType}/${event.resourceId}`}
                  </p>
                  <span className="timeline__meta">
                    {formatDateTime(event.timestampUnixMs)}
                  </span>
                </article>
              ))}
            </div>
          ) : (
            <EmptyState
              title="No recent kernel events"
              description="Once the kernel starts sending lifecycle updates, they’ll appear here and in the System view."
            />
          )}
        </Panel>
      </div>
    </div>
  );
}
