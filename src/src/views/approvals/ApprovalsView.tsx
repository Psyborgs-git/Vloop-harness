import { useCallback, useEffect, useMemo, useState } from "react";
import type { PendingApproval, WorkflowEventFrame } from "../../lib/api";
import {
  approveCheckpoint,
  getErrorMessage,
  listPendingApprovals,
  rejectCheckpoint,
} from "../../lib/api";
import { useWorkflowEvents } from "../../hooks/useWorkflowEvents";
import {
  EmptyState,
  InlineNotice,
  JsonBlock,
  PageHeader,
  Panel,
  StatusBadge,
  formatDateTime,
} from "../../components/ui";

// The Event_Router emits approval checkpoints under this canonical type
// (core/event_router.py -> WorkflowEventType.APPROVAL_REQUIRED). The approvals
// view filters the shared workflow-event stream by it to discover which runs
// have a checkpoint awaiting a decision (Requirements 8.2, 20.4).
const APPROVAL_REQUIRED_EVENT = "approval.required";

/** A pending approval enriched with the streamed event that announced it. */
interface ApprovalItem {
  runId: string;
  stepId: string;
  context: Record<string, unknown>;
  event: WorkflowEventFrame | null;
}

function approvalKey(runId: string, stepId: string): string {
  return `${runId}::${stepId}`;
}

export function ApprovalsView() {
  // Live event stream (shared hook, reused from the workflows view). We only
  // look at approval-required frames here (Req 20.4) — no direct kernel/db
  // access; approve/reject go through the Control_Plane HTTP API.
  const { events, status: streamStatus } = useWorkflowEvents();

  // Runs we actively poll for pending approvals: seeded from approval-required
  // events and by manual run-id entry (so approvals raised before this view
  // mounted can still be surfaced).
  const [watchedRunIds, setWatchedRunIds] = useState<string[]>([]);
  const [manualRunId, setManualRunId] = useState("");

  // Authoritative pending approvals per watched run, keyed by run id.
  const [pendingByRun, setPendingByRun] = useState<
    Record<string, PendingApproval[]>
  >({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Per-checkpoint decision inputs + in-flight state.
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [decided, setDecided] = useState<Record<string, string>>({});

  // The most recent approval-required event per checkpoint, for context/timing.
  const approvalEvents = useMemo(() => {
    const map = new Map<string, WorkflowEventFrame>();
    for (const event of events) {
      if (event.type !== APPROVAL_REQUIRED_EVENT || !event.step_id) {
        continue;
      }
      map.set(approvalKey(event.run_id, event.step_id), event);
    }
    return map;
  }, [events]);

  // Auto-watch any run that streams an approval-required event.
  useEffect(() => {
    const runIds = new Set<string>();
    for (const event of events) {
      if (event.type === APPROVAL_REQUIRED_EVENT) {
        runIds.add(event.run_id);
      }
    }
    if (runIds.size === 0) {
      return;
    }
    setWatchedRunIds((prev) => {
      const next = new Set(prev);
      let changed = false;
      for (const runId of runIds) {
        if (!next.has(runId)) {
          next.add(runId);
          changed = true;
        }
      }
      return changed ? Array.from(next) : prev;
    });
  }, [events]);

  const refreshRun = useCallback(async (runId: string) => {
    try {
      const pending = await listPendingApprovals(runId);
      setPendingByRun((prev) => ({ ...prev, [runId]: pending }));
      setError(null);
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    }
  }, []);

  const refreshAll = useCallback(async () => {
    if (watchedRunIds.length === 0) {
      setPendingByRun({});
      return;
    }
    setLoading(true);
    try {
      await Promise.all(watchedRunIds.map((runId) => refreshRun(runId)));
    } finally {
      setLoading(false);
    }
  }, [watchedRunIds, refreshRun]);

  // Refresh pending approvals whenever the watched set changes or a new
  // approval-required event arrives (the run's awaiting-approval set may have
  // changed on the Control_Plane).
  const approvalEventCount = approvalEvents.size;
  useEffect(() => {
    void refreshAll();
    // approvalEventCount is included so a newly-streamed checkpoint triggers a
    // re-fetch of the authoritative pending list.
  }, [refreshAll, approvalEventCount]);

  const handleAddRun = () => {
    const runId = manualRunId.trim();
    if (!runId) {
      return;
    }
    setWatchedRunIds((prev) => (prev.includes(runId) ? prev : [...prev, runId]));
    setManualRunId("");
  };

  const handleApprove = async (item: ApprovalItem) => {
    const key = approvalKey(item.runId, item.stepId);
    setBusyKey(key);
    try {
      const note = (notes[key] ?? "").trim();
      const edits = note ? { note } : undefined;
      await approveCheckpoint(item.runId, item.stepId, edits);
      setDecided((prev) => ({ ...prev, [key]: "Approved" }));
      setError(null);
      await refreshRun(item.runId);
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      setBusyKey(null);
    }
  };

  const handleReject = async (item: ApprovalItem) => {
    const key = approvalKey(item.runId, item.stepId);
    setBusyKey(key);
    try {
      const reason = (notes[key] ?? "").trim();
      await rejectCheckpoint(item.runId, item.stepId, reason);
      setDecided((prev) => ({ ...prev, [key]: "Rejected" }));
      setError(null);
      await refreshRun(item.runId);
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      setBusyKey(null);
    }
  };

  // Flatten the authoritative pending approvals into renderable items, enriched
  // with the streamed event context/timing when available.
  const items = useMemo<ApprovalItem[]>(() => {
    const flat: ApprovalItem[] = [];
    for (const runId of watchedRunIds) {
      for (const pending of pendingByRun[runId] ?? []) {
        const event =
          approvalEvents.get(approvalKey(runId, pending.step_id)) ?? null;
        flat.push({
          runId,
          stepId: pending.step_id,
          context: pending.context ?? {},
          event,
        });
      }
    }
    return flat;
  }, [watchedRunIds, pendingByRun, approvalEvents]);

  return (
    <div className="page-stack">
      <PageHeader
        title="Approvals"
        description="Review workflow steps awaiting a decision and approve or reject them. Driven entirely by Control_Plane HTTP + WebSocket APIs."
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
              onClick={() => void refreshAll()}
              disabled={loading || watchedRunIds.length === 0}
            >
              {loading ? "Refreshing…" : "Refresh"}
            </button>
          </div>
        }
      />

      {error ? (
        <InlineNotice tone="bad" title="Approval error">
          <p>{error}</p>
          <button
            className="button button--secondary"
            type="button"
            onClick={() => setError(null)}
            style={{ marginTop: 8 }}
          >
            Dismiss
          </button>
        </InlineNotice>
      ) : null}

      <Panel
        title="Watch a run"
        subtitle="Runs that stream an approval-required event are watched automatically. Add a run id to surface approvals raised before this view opened."
      >
        <div className="button-row" style={{ alignItems: "flex-end" }}>
          <div className="form-field" style={{ flex: 1, marginBottom: 0 }}>
            <label htmlFor="approval-run-id">Run id</label>
            <input
              id="approval-run-id"
              type="text"
              value={manualRunId}
              onChange={(event) => setManualRunId(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  handleAddRun();
                }
              }}
              placeholder="workflow run id"
              spellCheck={false}
              style={{ width: "100%", fontFamily: "var(--font-mono, monospace)" }}
            />
          </div>
          <button
            className="button button--secondary"
            type="button"
            onClick={handleAddRun}
            disabled={!manualRunId.trim()}
          >
            Watch run
          </button>
        </div>

        {watchedRunIds.length > 0 ? (
          <div className="button-row" style={{ marginTop: 12, flexWrap: "wrap" }}>
            {watchedRunIds.map((runId) => (
              <StatusBadge
                key={runId}
                tone="accent"
                label={`${runId.slice(0, 8)}…`}
              />
            ))}
          </div>
        ) : null}
      </Panel>

      <Panel
        title="Pending approvals"
        subtitle={`${items.length} checkpoint(s) awaiting a decision`}
      >
        {items.length === 0 ? (
          <EmptyState
            title="No pending approvals"
            description="When a workflow run reaches an approval checkpoint, it will appear here for review."
          />
        ) : (
          <div className="stack-list">
            {items.map((item) => {
              const key = approvalKey(item.runId, item.stepId);
              const outcome = decided[key];
              const busy = busyKey === key;
              return (
                <article
                  key={key}
                  className="list-action"
                  style={{
                    flexDirection: "column",
                    alignItems: "flex-start",
                    gap: 8,
                  }}
                >
                  <div
                    className="list-action__title-row"
                    style={{ width: "100%" }}
                  >
                    <strong className="mono">{item.stepId}</strong>
                    {outcome ? (
                      <StatusBadge
                        tone={outcome === "Approved" ? "good" : "bad"}
                        label={outcome}
                      />
                    ) : (
                      <StatusBadge status="awaiting-approval" />
                    )}
                  </div>
                  <p style={{ color: "var(--muted)" }}>
                    Run <span className="mono">{item.runId.slice(0, 8)}…</span>
                    {item.event
                      ? ` · requested ${formatDateTime(item.event.created_at)}`
                      : ""}
                  </p>
                  {item.event?.message ? <p>{item.event.message}</p> : null}

                  <div style={{ width: "100%" }}>
                    <strong style={{ fontSize: "0.82rem" }}>
                      Checkpoint context
                    </strong>
                    <JsonBlock
                      value={item.context}
                      emptyLabel="No context provided."
                    />
                  </div>

                  <div className="form-field" style={{ width: "100%" }}>
                    <label htmlFor={`note-${key}`}>
                      Note (edits on approve · reason on reject)
                    </label>
                    <textarea
                      id={`note-${key}`}
                      value={notes[key] ?? ""}
                      onChange={(event) =>
                        setNotes((prev) => ({
                          ...prev,
                          [key]: event.target.value,
                        }))
                      }
                      rows={2}
                      spellCheck={false}
                      disabled={Boolean(outcome)}
                      style={{ width: "100%" }}
                    />
                  </div>

                  <div className="button-row">
                    <button
                      className="button button--primary"
                      type="button"
                      onClick={() => void handleApprove(item)}
                      disabled={busy || Boolean(outcome)}
                    >
                      {busy ? "Working…" : "Approve"}
                    </button>
                    <button
                      className="button button--danger"
                      type="button"
                      onClick={() => void handleReject(item)}
                      disabled={busy || Boolean(outcome)}
                    >
                      {busy ? "Working…" : "Reject"}
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </Panel>
    </div>
  );
}
