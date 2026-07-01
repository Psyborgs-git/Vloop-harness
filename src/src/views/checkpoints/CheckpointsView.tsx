import { useCallback, useEffect, useState } from "react";
import type { Checkpoint } from "../../lib/api";
import {
  getErrorMessage,
  listCheckpoints,
  rollbackCheckpoint,
} from "../../lib/api";
import { useWorkflowEvents } from "../../hooks/useWorkflowEvents";
import {
  EmptyState,
  InlineNotice,
  KeyValueList,
  PageHeader,
  Panel,
  StatusBadge,
  formatDateTime,
} from "../../components/ui";

export function CheckpointsView() {
  // Live event stream (shared hook, reused across the orchestration views). We
  // use it only to live-refresh the selected run's checkpoint list when new
  // events land for it (Req 20.4) — no direct kernel/db access. Listing and
  // rollback are driven entirely through the Control_Plane HTTP API.
  const { events, status: streamStatus } = useWorkflowEvents();

  const [manualRunId, setManualRunId] = useState("");
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [checkpoints, setCheckpoints] = useState<Checkpoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Rollback confirmation + in-flight state, keyed by checkpoint id.
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [restored, setRestored] = useState<Checkpoint | null>(null);

  const refreshCheckpoints = useCallback(async (runId: string) => {
    setLoading(true);
    try {
      const next = await listCheckpoints(runId);
      setCheckpoints(next);
      setError(null);
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedRunId) {
      void refreshCheckpoints(selectedRunId);
    } else {
      setCheckpoints([]);
    }
  }, [selectedRunId, refreshCheckpoints]);

  // A new snapshot/checkpoint may be recorded as a run progresses; when a fresh
  // event lands for the selected run, re-fetch its authoritative checkpoint
  // list from the Control_Plane so the listing stays live.
  const runEventCount = selectedRunId
    ? events.filter((event) => event.run_id === selectedRunId).length
    : 0;
  useEffect(() => {
    if (selectedRunId && runEventCount > 0) {
      void refreshCheckpoints(selectedRunId);
    }
  }, [runEventCount, selectedRunId, refreshCheckpoints]);

  const handleLoadRun = () => {
    const runId = manualRunId.trim();
    if (!runId) {
      return;
    }
    setSelectedRunId(runId);
    setConfirmId(null);
    setRestored(null);
  };

  const handleRollback = async (checkpoint: Checkpoint) => {
    setBusyId(checkpoint.id);
    try {
      const result = await rollbackCheckpoint(checkpoint.id);
      setRestored(result);
      setConfirmId(null);
      setError(null);
      if (selectedRunId) {
        await refreshCheckpoints(selectedRunId);
      }
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="page-stack">
      <PageHeader
        title="Checkpoints"
        description="List a workflow run's recorded checkpoints and roll the workspace back to one. Driven entirely by Control_Plane HTTP + WebSocket APIs."
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
              onClick={() =>
                selectedRunId
                  ? void refreshCheckpoints(selectedRunId)
                  : undefined
              }
              disabled={loading || !selectedRunId}
            >
              {loading ? "Refreshing…" : "Refresh"}
            </button>
          </div>
        }
      />

      {error ? (
        <InlineNotice tone="bad" title="Checkpoint error">
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

      {restored ? (
        <InlineNotice tone="good" title="Rollback requested">
          <p>
            The Kernel was asked to restore workspace{" "}
            <span className="mono">{restored.workspace_id}</span> to checkpoint{" "}
            <span className="mono">{restored.id.slice(0, 8)}…</span>.
          </p>
          <button
            className="button button--secondary"
            type="button"
            onClick={() => setRestored(null)}
            style={{ marginTop: 8 }}
          >
            Dismiss
          </button>
        </InlineNotice>
      ) : null}

      <Panel
        title="Select a run"
        subtitle="Enter a workflow run id to list the checkpoints recorded for it."
      >
        <div className="button-row" style={{ alignItems: "flex-end" }}>
          <div className="form-field" style={{ flex: 1, marginBottom: 0 }}>
            <label htmlFor="checkpoint-run-id">Run id</label>
            <input
              id="checkpoint-run-id"
              type="text"
              value={manualRunId}
              onChange={(event) => setManualRunId(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  handleLoadRun();
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
            onClick={handleLoadRun}
            disabled={!manualRunId.trim()}
          >
            List checkpoints
          </button>
        </div>

        {selectedRunId ? (
          <div className="button-row" style={{ marginTop: 12 }}>
            <StatusBadge tone="accent" label={`Run ${selectedRunId.slice(0, 8)}…`} />
          </div>
        ) : null}
      </Panel>

      {selectedRunId ? (
        <Panel
          title="Checkpoints"
          subtitle={`${checkpoints.length} checkpoint(s) recorded for this run`}
        >
          {checkpoints.length === 0 ? (
            <EmptyState
              title="No checkpoints"
              description="This run has no recorded checkpoints yet. Checkpoints are snapshotted before workspace mutations."
            />
          ) : (
            <div className="stack-list">
              {checkpoints.map((checkpoint) => {
                const confirming = confirmId === checkpoint.id;
                const busy = busyId === checkpoint.id;
                return (
                  <article
                    key={checkpoint.id}
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
                      <strong className="mono">
                        {checkpoint.id.slice(0, 8)}…
                      </strong>
                      {restored?.id === checkpoint.id ? (
                        <StatusBadge tone="good" label="Restored" />
                      ) : null}
                    </div>

                    <KeyValueList
                      items={[
                        {
                          label: "Checkpoint id",
                          value: (
                            <span className="mono">{checkpoint.id}</span>
                          ),
                        },
                        {
                          label: "Workspace",
                          value: (
                            <span className="mono">
                              {checkpoint.workspace_id}
                            </span>
                          ),
                        },
                        {
                          label: "Snapshot ref",
                          value: (
                            <span className="mono">
                              {checkpoint.kernel_snapshot_ref}
                            </span>
                          ),
                        },
                        {
                          label: "Created",
                          value: formatDateTime(checkpoint.created_at),
                        },
                      ]}
                    />

                    {confirming ? (
                      <div
                        className="button-row"
                        style={{ alignItems: "center" }}
                      >
                        <span style={{ color: "var(--muted)" }}>
                          Roll the workspace back to this checkpoint?
                        </span>
                        <button
                          className="button button--danger"
                          type="button"
                          onClick={() => void handleRollback(checkpoint)}
                          disabled={busy}
                        >
                          {busy ? "Rolling back…" : "Confirm rollback"}
                        </button>
                        <button
                          className="button button--secondary"
                          type="button"
                          onClick={() => setConfirmId(null)}
                          disabled={busy}
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <div className="button-row">
                        <button
                          className="button button--secondary"
                          type="button"
                          onClick={() => setConfirmId(checkpoint.id)}
                        >
                          Roll back
                        </button>
                      </div>
                    )}
                  </article>
                );
              })}
            </div>
          )}
        </Panel>
      ) : null}
    </div>
  );
}
