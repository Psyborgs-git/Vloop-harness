import type {
  HealthSnapshot,
  KernelEventRecord,
  SessionSnapshot,
  SystemSnapshot,
  WindowSnapshot,
} from '../lib/api';
import {
  EmptyState,
  InlineNotice,
  JsonBlock,
  KeyValueList,
  PageHeader,
  Panel,
  StatusBadge,
  formatDateTime,
  formatRelativeTime,
} from '../components/ui';

interface SystemViewProps {
  system: SystemSnapshot | null;
  systemError: string | null;
  warning: string | null;
}

export function SystemView({ system, systemError, warning }: SystemViewProps) {
  const health = system?.health ?? null;
  const session = system?.session ?? null;
  const windowState = system?.window ?? null;
  const recentEvents = system?.recentEvents ?? [];

  return (
    <div className="page-stack">
      <PageHeader
        title="System"
        description="Inspect the Control Plane, kernel session, pywebview shell state, and the latest event traffic."
      />

      {warning ? (
        <InlineNotice tone="warn" title="Configuration APIs are incomplete in this build">
          <p>{warning}</p>
        </InlineNotice>
      ) : null}

      {systemError ? (
        <InlineNotice tone="bad" title="System refresh failed">
          <p>{systemError}</p>
        </InlineNotice>
      ) : null}

      {!system ? (
        <EmptyState
          title="Waiting for Control Plane status"
          description="The frontend will populate health, session, window, and event details as soon as the Python Control Plane responds."
        />
      ) : (
        <>
          <div className="overview-grid">
            <Panel title="Control Plane health" subtitle="Current registration and shell-serving status.">
              <KeyValueList items={buildHealthItems(health)} />
            </Panel>
            <Panel title="Kernel session" subtitle="Session identifiers, granted scopes, and heartbeat timing.">
              <KeyValueList items={buildSessionItems(session)} />
            </Panel>
            <Panel title="Window state" subtitle="Pywebview shell lifecycle and current loaded URL.">
              <KeyValueList items={buildWindowItems(windowState)} />
            </Panel>
            <Panel title="Kernel active config" subtitle="Injected runtime metadata the Control Plane currently sees.">
              <KeyValueList
                items={[
                  {
                    label: 'IPC endpoint',
                    value: <span className="mono break-anywhere">{session?.activeConfig?.ipcEndpoint ?? '—'}</span>,
                  },
                  {
                    label: 'Boot ID',
                    value: <span className="mono break-anywhere">{session?.activeConfig?.bootId ?? '—'}</span>,
                  },
                  {
                    label: 'Runtime root',
                    value: <span className="mono break-anywhere">{session?.activeConfig?.runtimeRoot ?? '—'}</span>,
                  },
                  {
                    label: 'Available runtimes',
                    value: session?.activeConfig?.availableRuntimes.length
                      ? session.activeConfig.availableRuntimes.join(', ')
                      : '—',
                  },
                ]}
              />
              <details className="details-block">
                <summary>Feature flags</summary>
                <JsonBlock value={session?.activeConfig?.features ?? null} emptyLabel="No active feature flags." />
              </details>
            </Panel>
          </div>

          <Panel
            title={`Recent events (${system.eventCount})`}
            subtitle="Newest kernel and Control Plane events first, including resource targets and event attributes."
          >
            {recentEvents.length > 0 ? (
              <div className="timeline">
                {recentEvents.map((event) => (
                  <article className="timeline__item" key={`${event.eventId}-${event.timestampUnixMs}`}>
                    <div className="timeline__title-row">
                      <strong>{event.eventType}</strong>
                      <StatusBadge status={event.status} />
                    </div>
                    <p>{event.message || `${event.resourceType}/${event.resourceId}`}</p>
                    <div className="timeline__meta-row">
                      <span className="timeline__meta">
                        {formatDateTime(event.timestampUnixMs)}
                      </span>
                      <span className="timeline__meta">
                        {event.resourceType}/{event.resourceId}
                      </span>
                      <span className="timeline__meta">
                        {formatRelativeTime(event.timestampUnixMs)}
                      </span>
                    </div>
                    {Object.keys(event.attributes).length > 0 ? (
                      <details className="details-block details-block--nested">
                        <summary>Attributes</summary>
                        <JsonBlock value={event.attributes} />
                      </details>
                    ) : null}
                  </article>
                ))}
              </div>
            ) : (
              <EmptyState
                title="No recent events"
                description="As the Control Plane receives kernel lifecycle traffic, those events will appear here automatically."
              />
            )}
          </Panel>
        </>
      )}
    </div>
  );
}

function buildHealthItems(health: HealthSnapshot | null) {
  return [
    {
      label: 'Status',
      value: <StatusBadge status={health?.status ?? 'unknown'} />,
    },
    {
      label: 'Version',
      value: health?.version ?? '—',
    },
    {
      label: 'Kernel endpoint',
      value: <span className="mono break-anywhere">{health?.kernelEndpoint ?? '—'}</span>,
    },
    {
      label: 'HTTP base URL',
      value: <span className="mono break-anywhere">{health?.httpBaseUrl ?? '—'}</span>,
    },
    {
      label: 'Shell URL',
      value: <span className="mono break-anywhere">{health?.shellUrl ?? '—'}</span>,
    },
    {
      label: 'Session ID',
      value: <span className="mono break-anywhere">{health?.sessionId ?? '—'}</span>,
    },
    {
      label: 'Last error',
      value: health?.lastError ?? 'None',
    },
  ];
}

function buildSessionItems(session: SessionSnapshot | null) {
  return [
    {
      label: 'Status',
      value: <StatusBadge status={session?.status ?? 'unknown'} />,
    },
    {
      label: 'Granted scopes',
      value: session?.grantedScopes.length ? session.grantedScopes.join(', ') : '—',
    },
    {
      label: 'Registered at',
      value: session?.lastRegisteredAtUnixMs
        ? formatDateTime(session.lastRegisteredAtUnixMs)
        : '—',
    },
    {
      label: 'Last heartbeat',
      value: session?.lastHeartbeatAtUnixMs
        ? formatDateTime(session.lastHeartbeatAtUnixMs)
        : '—',
    },
    {
      label: 'Last error',
      value: session?.lastError ?? 'None',
    },
  ];
}

function buildWindowItems(windowState: WindowSnapshot | null) {
  return [
    {
      label: 'Backend',
      value: windowState?.backend ?? '—',
    },
    {
      label: 'Visible',
      value: <StatusBadge status={windowState?.isOpen ?? false} label={windowState?.isOpen ? 'Open' : 'Hidden'} />,
    },
    {
      label: 'Open requests',
      value: String(windowState?.openRequests ?? 0),
    },
    {
      label: 'Last open reason',
      value: windowState?.lastOpenReason ?? '—',
    },
    {
      label: 'Last opened',
      value: windowState?.lastOpenedAtUnixMs
        ? formatDateTime(windowState.lastOpenedAtUnixMs)
        : '—',
    },
    {
      label: 'Last focused',
      value: windowState?.lastFocusedAtUnixMs
        ? formatDateTime(windowState.lastFocusedAtUnixMs)
        : '—',
    },
    {
      label: 'Loaded URL',
      value: <span className="mono break-anywhere">{windowState?.loadedUrl ?? '—'}</span>,
    },
  ];
}
