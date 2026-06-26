import { useCallback, useEffect, useState } from 'react';
import {
  getErrorMessage,
  getInvocation,
  getInvocationEvents,
  getUsageStats,
  type InvocationEvent,
  type InvocationRecord,
  type UsageStats,
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
  formatDuration,
} from '../components/ui';

export function UsageView() {
  const [usageStats, setUsageStats] = useState<UsageStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedInvocationId, setExpandedInvocationId] = useState<string | null>(
    null,
  );
  const [expandedInvocation, setExpandedInvocation] =
    useState<InvocationRecord | null>(null);
  const [expandedEvents, setExpandedEvents] = useState<InvocationEvent[]>([]);
  const [expandedError, setExpandedError] = useState<string | null>(null);

  const fetchUsage = useCallback(async () => {
    setLoading(true);
    try {
      const stats = await getUsageStats();
      setUsageStats(stats);
      setError(null);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchUsage();
  }, [fetchUsage]);

  useEffect(() => {
    if (!expandedInvocationId) {
      setExpandedInvocation(null);
      setExpandedEvents([]);
      setExpandedError(null);
      return;
    }

    let cancelled = false;
    setExpandedError(null);

    Promise.all([
      getInvocation(expandedInvocationId),
      getInvocationEvents(expandedInvocationId),
    ])
      .then(([invocation, events]) => {
        if (!cancelled) {
          setExpandedInvocation(invocation);
          setExpandedEvents(events);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setExpandedError(getErrorMessage(err));
        }
      });

    return () => {
      cancelled = true;
    };
  }, [expandedInvocationId]);

  return (
    <div className="page-stack">
      <PageHeader
        title="Usage"
        description="Token usage aggregated across all invocations, broken down by provider and agent, with trace-level details."
        actions={
          <button
            className="button button--secondary"
            type="button"
            onClick={() => {
              void fetchUsage();
            }}
            disabled={loading}
          >
            {loading ? 'Loading…' : 'Refresh'}
          </button>
        }
      />

      {error ? (
        <InlineNotice tone="bad" title="Could not load usage statistics">
          <p>{error}</p>
        </InlineNotice>
      ) : null}

      {!usageStats && !loading ? (
        <EmptyState
          title="No usage data available"
          description="Run some agent invocations to collect token usage statistics."
        />
      ) : null}

      {usageStats ? (
        <>
          <div className="overview-grid">
            <Panel
              title="Total tokens"
              subtitle="Aggregate across all invocations"
            >
              <KeyValueList
                items={[
                  {
                    label: 'Total tokens',
                    value: (
                      <strong>{usageStats.totalTokens.toLocaleString()}</strong>
                    ),
                  },
                  {
                    label: 'Prompt tokens',
                    value: usageStats.totalPromptTokens.toLocaleString(),
                  },
                  {
                    label: 'Completion tokens',
                    value: usageStats.totalCompletionTokens.toLocaleString(),
                  },
                  {
                    label: 'Invocations with usage',
                    value: String(usageStats.invocationCount),
                  },
                ]}
              />
            </Panel>

            <Panel
              title="By provider"
              subtitle={`${usageStats.byProvider.length} providers with usage data`}
            >
              {usageStats.byProvider.length > 0 ? (
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Provider</th>
                      <th>Type</th>
                      <th>Invocations</th>
                      <th>Tokens</th>
                    </tr>
                  </thead>
                  <tbody>
                    {usageStats.byProvider.map((provider) => (
                      <tr key={provider.providerId}>
                        <td>
                          <strong>{provider.providerName}</strong>
                        </td>
                        <td>
                          <StatusBadge label={provider.providerType} />
                        </td>
                        <td>{provider.invocationCount}</td>
                        <td>{provider.totalTokens.toLocaleString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p className="muted-text">No provider usage data yet.</p>
              )}
            </Panel>

            <Panel
              title="By agent"
              subtitle={`${usageStats.byAgent.length} agents with usage data`}
            >
              {usageStats.byAgent.length > 0 ? (
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Agent</th>
                      <th>Invocations</th>
                      <th>Tokens</th>
                    </tr>
                  </thead>
                  <tbody>
                    {usageStats.byAgent.map((agent) => (
                      <tr key={agent.agentId}>
                        <td>
                          <strong>{agent.agentName}</strong>
                        </td>
                        <td>{agent.invocationCount}</td>
                        <td>{agent.totalTokens.toLocaleString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p className="muted-text">No agent usage data yet.</p>
              )}
            </Panel>
          </div>

          <Panel
            title={`Recent invocations (${usageStats.recentInvocations.length})`}
            subtitle="Last 20 invocations with token usage data. Click a row to expand trace details."
          >
            {usageStats.recentInvocations.length > 0 ? (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Agent</th>
                    <th>Provider</th>
                    <th>Model</th>
                    <th>Prompt</th>
                    <th>Completion</th>
                    <th>Total</th>
                  </tr>
                </thead>
                <tbody>
                  {usageStats.recentInvocations.map((inv) => (
                    <tr
                      key={inv.invocationId}
                      className={
                        expandedInvocationId === inv.invocationId
                          ? 'is-selected clickable'
                          : 'clickable'
                      }
                      onClick={() =>
                        setExpandedInvocationId(
                          expandedInvocationId === inv.invocationId
                            ? null
                            : inv.invocationId,
                        )
                      }
                    >
                      <td className="muted-text">
                        {formatDateTime(inv.createdAt)}
                      </td>
                      <td>
                        <strong>{inv.agentName || inv.agentId}</strong>
                      </td>
                      <td>
                        <StatusBadge label={inv.providerName || inv.providerId} />
                      </td>
                      <td className="mono">{inv.model}</td>
                      <td>{inv.promptTokens.toLocaleString()}</td>
                      <td>{inv.completionTokens.toLocaleString()}</td>
                      <td>
                        <strong>{inv.totalTokens.toLocaleString()}</strong>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="muted-text">
                No recent invocations with usage data.
              </p>
            )}

            {expandedInvocationId ? (
              <div className="trace-expanded">
                {expandedError ? (
                  <InlineNotice
                    tone="warn"
                    title="Could not load invocation trace"
                  >
                    <p>{expandedError}</p>
                  </InlineNotice>
                ) : null}

                {expandedInvocation ? (
                  <>
                    <div className="status-strip">
                      <StatusBadge status={expandedInvocation.status} />
                      <span className="muted-text">
                        {expandedInvocation.resolvedModel ?? '—'}
                      </span>
                      <span className="muted-text">
                        {formatDuration(
                          expandedInvocation.startedAt ??
                            expandedInvocation.createdAt,
                          expandedInvocation.finishedAt,
                        )}
                      </span>
                    </div>

                    <h3 className="section-title">Trace timeline</h3>
                    {expandedEvents.length > 0 ? (
                      <div className="timeline">
                        {expandedEvents.map((event, idx) => {
                          const nextEvent = expandedEvents[idx + 1];
                          const stepDuration =
                            nextEvent?.elapsedMs != null &&
                            event.elapsedMs != null
                              ? nextEvent.elapsedMs - event.elapsedMs
                              : null;

                          return (
                            <article
                              className="timeline__item"
                              key={`${event.seq}-${event.type}`}
                            >
                              <div className="timeline__title-row">
                                <strong>
                                  {event.seq}. {event.type}
                                </strong>
                                <span className="timeline__meta">
                                  {formatDateTime(event.createdAt)}
                                </span>
                              </div>
                              <p>{event.message}</p>
                              <div className="timeline__meta-row">
                                {event.elapsedMs != null ? (
                                  <span className="timeline__meta">
                                    Elapsed: {event.elapsedMs} ms
                                  </span>
                                ) : null}
                                {stepDuration != null && stepDuration >= 0 ? (
                                  <span className="timeline__meta">
                                    Step: {stepDuration} ms
                                  </span>
                                ) : null}
                              </div>
                              {Object.keys(event.payload).length > 0 ? (
                                <details className="details-block details-block--nested">
                                  <summary>Payload</summary>
                                  <JsonBlock value={event.payload} />
                                </details>
                              ) : null}
                            </article>
                          );
                        })}
                      </div>
                    ) : (
                      <p className="muted-text">
                        No timeline events recorded for this invocation.
                      </p>
                    )}

                    {expandedInvocation.reasoningText ? (
                      <details className="details-block">
                        <summary>Reasoning trace</summary>
                        <pre className="code-block code-block--wrap">
                          {expandedInvocation.reasoningText}
                        </pre>
                      </details>
                    ) : null}

                    {expandedInvocation.usage ? (
                      <details className="details-block">
                        <summary>Raw usage data</summary>
                        <JsonBlock value={expandedInvocation.usage} />
                      </details>
                    ) : null}
                  </>
                ) : (
                  <p className="muted-text">Loading invocation details…</p>
                )}
              </div>
            ) : null}
          </Panel>
        </>
      ) : null}
    </div>
  );
}
