import { useMemo } from "react";
import type { WorkflowEventFrame } from "../../lib/api";
import { useWorkflowEvents } from "../../hooks/useWorkflowEvents";
import {
  EmptyState,
  JsonBlock,
  KeyValueList,
  PageHeader,
  Panel,
  StatusBadge,
  formatDateTime,
} from "../../components/ui";

// The Event_Router emits budget/rate status frames under these canonical types
// (core/event_router.py -> WorkflowEventType.BUDGET_STATUS / RATE_LIMIT_STATUS).
// The budgets view filters the shared workflow-event stream by them to surface
// per-run budget consumption and rate-limit activity (Requirements 7.5, 20.4).
// The Budget_Tracker/Rate_Limiter emit them (core/inference_gateway.py); the
// WebSocket push channel fans them out, so the stream is the primary source.
const BUDGET_STATUS_EVENT = "budget.status";
const RATE_LIMIT_STATUS_EVENT = "rate_limit.status";

/** The budget snapshot carried on a `budget.status` event payload. */
interface BudgetSnapshot {
  max_tokens: number | null;
  max_cost: number | null;
  used_tokens: number;
  used_cost: number;
}

/** Aggregated budget state for a single run, from its latest budget event. */
interface RunBudgetSummary {
  runId: string;
  definitionId: string | null;
  budget: BudgetSnapshot | null;
  blocked: boolean;
  skipped: boolean;
  reason: string | null;
  message: string;
  updatedAt: string;
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value ? value : null;
}

/** Extract a {@link BudgetSnapshot} from a `budget.status` event payload. */
function readBudgetSnapshot(payload: Record<string, unknown>): BudgetSnapshot | null {
  const raw = payload.budget;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    return null;
  }
  const budget = raw as Record<string, unknown>;
  return {
    max_tokens: asNumber(budget.max_tokens),
    max_cost: asNumber(budget.max_cost),
    used_tokens: asNumber(budget.used_tokens) ?? 0,
    used_cost: asNumber(budget.used_cost) ?? 0,
  };
}

/** Format a token allowance, treating a null limit as "unbounded" (Req 7.1). */
function formatTokens(used: number, limit: number | null): string {
  if (limit === null) {
    return `${used.toLocaleString()} / ∞`;
  }
  return `${used.toLocaleString()} / ${limit.toLocaleString()}`;
}

/** Format a cost allowance, treating a null limit as "unbounded" (Req 7.1). */
function formatCost(used: number, limit: number | null): string {
  const usedText = `$${used.toFixed(4)}`;
  if (limit === null) {
    return `${usedText} / ∞`;
  }
  return `${usedText} / $${limit.toFixed(4)}`;
}

function remainingTokens(budget: BudgetSnapshot): string {
  if (budget.max_tokens === null) {
    return "Unbounded";
  }
  return Math.max(budget.max_tokens - budget.used_tokens, 0).toLocaleString();
}

function remainingCost(budget: BudgetSnapshot): string {
  if (budget.max_cost === null) {
    return "Unbounded";
  }
  return `$${Math.max(budget.max_cost - budget.used_cost, 0).toFixed(4)}`;
}

export function BudgetsView() {
  // Live event stream (shared hook, reused across the orchestration views). We
  // only look at budget/rate status frames here (Req 20.4) — no direct
  // kernel/db access; everything is driven from the Control_Plane WebSocket
  // push channel.
  const { events, status: streamStatus, clear } = useWorkflowEvents();

  // Budget status frames, oldest first, as streamed.
  const budgetEvents = useMemo(
    () => events.filter((event) => event.type === BUDGET_STATUS_EVENT),
    [events],
  );

  // Rate-limit status frames, oldest first, as streamed.
  const rateEvents = useMemo(
    () => events.filter((event) => event.type === RATE_LIMIT_STATUS_EVENT),
    [events],
  );

  // A combined chronological feed of budget + rate status events (newest last
  // in the stream; we render newest first for the feed).
  const statusFeed = useMemo(() => {
    const combined = [...budgetEvents, ...rateEvents];
    // The stream is already append-ordered; preserve arrival order but show the
    // most recent activity first.
    return combined
      .map((event) => ({ event, index: events.indexOf(event) }))
      .sort((a, b) => b.index - a.index)
      .map((entry) => entry.event);
  }, [budgetEvents, rateEvents, events]);

  // Per-run budget consumption from the latest budget.status event for each
  // run (spend, limit, remaining, and any blocked/skipped status flags).
  const runSummaries = useMemo<RunBudgetSummary[]>(() => {
    const byRun = new Map<string, RunBudgetSummary>();
    for (const event of budgetEvents) {
      const payload = event.payload ?? {};
      const snapshot = readBudgetSnapshot(payload);
      // A run with only "skipped" events keeps its last known snapshot (if any)
      // rather than dropping the budget figures.
      const existing = byRun.get(event.run_id);
      byRun.set(event.run_id, {
        runId: event.run_id,
        definitionId: asString(payload.definition_id) ?? existing?.definitionId ?? null,
        budget: snapshot ?? existing?.budget ?? null,
        blocked: payload.blocked === true,
        skipped: payload.skipped === true,
        reason: asString(payload.reason),
        message: event.message,
        updatedAt: event.created_at,
      });
    }
    return Array.from(byRun.values());
  }, [budgetEvents]);

  return (
    <div className="page-stack">
      <PageHeader
        title="Budgets"
        description="Track per-run budget consumption and live budget/rate-limit status. Driven entirely by Control_Plane HTTP + WebSocket APIs."
        actions={
          <div className="button-row">
            <StatusBadge
              tone={streamStatus === "open" ? "good" : "warn"}
              label={
                streamStatus === "open"
                  ? "Live events connected"
                  : streamStatus === "connecting"
                    ? "Connecting…"
                    : "Live events offline"
              }
            />
            <button
              className="button button--secondary"
              type="button"
              onClick={clear}
              disabled={events.length === 0}
            >
              Clear feed
            </button>
          </div>
        }
      />

      <Panel
        title="Budget usage"
        subtitle={`${runSummaries.length} run(s) with reported budget activity`}
      >
        {runSummaries.length === 0 ? (
          <EmptyState
            title="No budget activity yet"
            description="When a workflow run reports budget usage or a budget is enforced, its consumption will appear here."
          />
        ) : (
          <div className="stack-list">
            {runSummaries.map((summary) => (
              <article
                key={summary.runId}
                className="list-action"
                style={{
                  flexDirection: "column",
                  alignItems: "flex-start",
                  gap: 8,
                }}
              >
                <div className="list-action__title-row" style={{ width: "100%" }}>
                  <strong className="mono">{summary.runId.slice(0, 8)}…</strong>
                  {summary.blocked ? (
                    <StatusBadge tone="bad" label="Budget exceeded" />
                  ) : summary.skipped ? (
                    <StatusBadge tone="warn" label="Check skipped" />
                  ) : (
                    <StatusBadge tone="good" label="Within budget" />
                  )}
                </div>
                <p style={{ color: "var(--muted)" }}>
                  {summary.definitionId
                    ? `Definition ${summary.definitionId.slice(0, 8)}… · `
                    : ""}
                  updated {formatDateTime(summary.updatedAt)}
                </p>
                {summary.message ? <p>{summary.message}</p> : null}
                {summary.skipped && summary.reason ? (
                  <p style={{ color: "var(--muted)" }}>Reason: {summary.reason}</p>
                ) : null}

                {summary.budget ? (
                  <KeyValueList
                    items={[
                      {
                        label: "Tokens (used / limit)",
                        value: formatTokens(
                          summary.budget.used_tokens,
                          summary.budget.max_tokens,
                        ),
                      },
                      {
                        label: "Tokens remaining",
                        value: remainingTokens(summary.budget),
                      },
                      {
                        label: "Cost (used / limit)",
                        value: formatCost(
                          summary.budget.used_cost,
                          summary.budget.max_cost,
                        ),
                      },
                      {
                        label: "Cost remaining",
                        value: remainingCost(summary.budget),
                      },
                    ]}
                  />
                ) : (
                  <p style={{ color: "var(--muted)" }}>
                    No budget figures reported for this run yet.
                  </p>
                )}
              </article>
            ))}
          </div>
        )}
      </Panel>

      <Panel
        title="Budget & rate-limit status"
        subtitle={`${statusFeed.length} status event(s) · ${rateEvents.length} rate-limit`}
      >
        {statusFeed.length === 0 ? (
          <EmptyState
            title="No status events yet"
            description="Budget checks and rate-limit delays will stream in here as workflow runs make model calls."
          />
        ) : (
          <div
            style={{
              maxHeight: 360,
              overflowY: "auto",
              background: "var(--color-bg-inset)",
              padding: 12,
              borderRadius: 6,
            }}
          >
            <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
              {statusFeed.map((event) => (
                <li
                  key={`${event.run_id}-${event.type}-${event.seq}`}
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: 4,
                    padding: "8px 0",
                    borderBottom: "1px solid var(--border, #2222)",
                  }}
                >
                  <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <StatusBadge
                      tone={event.type === RATE_LIMIT_STATUS_EVENT ? "warn" : "accent"}
                      label={
                        event.type === RATE_LIMIT_STATUS_EVENT
                          ? "Rate limit"
                          : "Budget"
                      }
                    />
                    <span className="mono" style={{ color: "var(--muted)" }}>
                      {event.run_id.slice(0, 8)}…
                    </span>
                    <span style={{ flex: 1 }}>{event.message}</span>
                    <span style={{ color: "var(--muted)", fontSize: "0.8rem" }}>
                      {formatDateTime(event.created_at)}
                    </span>
                  </div>
                  <JsonBlock value={event.payload} emptyLabel="No payload." />
                </li>
              ))}
            </ul>
          </div>
        )}
      </Panel>
    </div>
  );
}
