import type {
  InvocationEvent,
  InvocationRecord,
  ProviderConfig,
} from "../../lib/api";
import {
  EmptyState,
  InlineNotice,
  JsonBlock,
  KeyValueList,
  StatusBadge,
  formatDateTime,
  formatDuration,
} from "../../components/ui";

interface InvocationDetailsProps {
  invocation: InvocationRecord | null;
  events: InvocationEvent[];
  providerMap: Map<string, ProviderConfig>;
}

export function InvocationDetails({
  invocation,
  events,
  providerMap,
}: InvocationDetailsProps) {
  if (!invocation) {
    return (
      <EmptyState
        title="No invocation selected"
        description="Run the current agent or choose a recent run to inspect its output, reasoning trace, and timeline."
      />
    );
  }

  return (
    <div className="stack-list stack-list--plain">
      <div className="status-strip">
        <StatusBadge status={invocation.status} />
        <span className="muted-text">
          {invocation.resolvedModel ?? "Model pending"}
        </span>
        <span className="muted-text">
          {formatDuration(
            invocation.startedAt ?? invocation.createdAt,
            invocation.finishedAt,
          )}
        </span>
      </div>

      <KeyValueList
        items={[
          {
            label: "Provider",
            value:
              providerMap.get(invocation.providerId)?.name ??
              invocation.providerId,
          },
          {
            label: "Created",
            value: formatDateTime(invocation.createdAt),
          },
          {
            label: "Started",
            value: formatDateTime(invocation.startedAt),
          },
          {
            label: "Finished",
            value: formatDateTime(invocation.finishedAt),
          },
        ]}
      />

      {invocation.errorMessage ? (
        <InlineNotice
          tone="bad"
          title={invocation.errorCode ?? "Invocation failed"}
        >
          <p>{invocation.errorMessage}</p>
        </InlineNotice>
      ) : null}

      {invocation.outputText ? (
        <div>
          <h3 className="section-title">Output text</h3>
          <pre className="code-block code-block--wrap">
            {invocation.outputText}
          </pre>
        </div>
      ) : null}

      {invocation.outputJson ? (
        <div>
          <h3 className="section-title">Parsed JSON</h3>
          <JsonBlock value={invocation.outputJson} />
        </div>
      ) : null}

      {invocation.reasoningText ? (
        <details className="details-block" open>
          <summary>Reasoning trace</summary>
          <pre className="code-block code-block--wrap">
            {invocation.reasoningText}
          </pre>
        </details>
      ) : null}

      <details className="details-block">
        <summary>Resolved configuration</summary>
        <JsonBlock value={invocation.resolvedConfig} />
      </details>

      {invocation.usage ? (
        <details className="details-block">
          <summary>Usage</summary>
          <JsonBlock value={invocation.usage} />
        </details>
      ) : null}

      <div>
        <h3 className="section-title">Invocation timeline</h3>
        {events.length > 0 ? (
          <div className="timeline">
            {events.map((event) => (
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
                {Object.keys(event.payload).length > 0 ? (
                  <details className="details-block details-block--nested">
                    <summary>Payload</summary>
                    <JsonBlock value={event.payload} />
                  </details>
                ) : null}
              </article>
            ))}
          </div>
        ) : (
          <p className="muted-text">
            Timeline events will appear after the Control Plane records them for
            this invocation.
          </p>
        )}
      </div>
    </div>
  );
}
