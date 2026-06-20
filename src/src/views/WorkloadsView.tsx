import { useCallback, useEffect, useRef, useState } from "react";
import type { WorkloadLogsResponse, WorkloadRecord } from "../lib/api";
import {
  createWorkload,
  getWorkloadLogs,
  listWorkloads,
  startWorkload,
  stopWorkload,
} from "../lib/api";
import {
  EmptyState,
  InlineNotice,
  PageHeader,
  Panel,
  StatusBadge,
} from "../components/ui";

export function WorkloadsView() {
  const [workloads, setWorkloads] = useState<WorkloadRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [image, setImage] = useState("nginx:alpine");
  const [command, setCommand] = useState("");
  const [port, setPort] = useState("80");
  const [creating, setCreating] = useState(false);
  const [selectedLogs, setSelectedLogs] = useState<WorkloadLogsResponse | null>(null);
  const [logsLoading, setLogsLoading] = useState(false);
  const logsRef = useRef<HTMLDivElement>(null);

  const refresh = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const next = await listWorkloads();
      setWorkloads(next);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const timer = window.setInterval(() => void refresh(true), 5000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    if (logsRef.current) {
      logsRef.current.scrollTop = logsRef.current.scrollHeight;
    }
  }, [selectedLogs?.logs]);

  const handleCreate = async () => {
    setCreating(true);
    setError(null);
    try {
      const commandList = command.trim()
        ? command.split(" ").filter(Boolean)
        : [];
      const ports = port.trim() ? [Number.parseInt(port.trim(), 10)] : [];
      await createWorkload({
        image: image.trim() || "nginx:alpine",
        command: commandList,
        ports,
        environment: {},
        class: "PREVIEW",
      });
      await refresh();
      setImage("nginx:alpine");
      setCommand("");
      setPort("80");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setCreating(false);
    }
  };

  const handleStart = async (workloadId: string) => {
    try {
      await startWorkload(workloadId);
      await refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleStop = async (workloadId: string) => {
    try {
      await stopWorkload(workloadId);
      await refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleViewLogs = async (workloadId: string) => {
    setLogsLoading(true);
    try {
      const logsResponse = await getWorkloadLogs(workloadId);
      setSelectedLogs(logsResponse);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLogsLoading(false);
    }
  };

  const stateTone = (state: string) => {
    switch (state) {
      case "running":
        return "good";
      case "failed":
        return "bad";
      case "starting":
        return "accent";
      case "completed":
        return "neutral";
      default:
        return "neutral";
    }
  };

  return (
    <div className="page-stack">
      <PageHeader
        title="Workloads"
        description="Create, run, and inspect Docker-based workloads backed by the kernel orchestrator."
        actions={
          <button
            className="button button--secondary"
            type="button"
            onClick={() => void refresh()}
            disabled={loading}
          >
            {loading ? "Refreshing…" : "Refresh"}
          </button>
        }
      />

      {error ? (
        <InlineNotice tone="bad" title="Workload error">
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

      <Panel title="Create workload" subtitle="Launch a Docker container from an image.">
        <div className="form-grid">
          <div className="form-field">
            <label htmlFor="w-image">Image</label>
            <input
              id="w-image"
              type="text"
              value={image}
              onChange={(e) => setImage(e.target.value)}
              placeholder="nginx:alpine"
            />
          </div>
          <div className="form-field">
            <label htmlFor="w-command">Command</label>
            <input
              id="w-command"
              type="text"
              value={command}
              onChange={(e) => setCommand(e.target.value)}
              placeholder="(empty = image default)"
            />
          </div>
          <div className="form-field">
            <label htmlFor="w-port">Port</label>
            <input
              id="w-port"
              type="number"
              value={port}
              onChange={(e) => setPort(e.target.value)}
              placeholder="80"
            />
          </div>
        </div>
        <div style={{ marginTop: 12 }}>
          <button
            className="button button--primary"
            type="button"
            onClick={() => void handleCreate()}
            disabled={creating}
          >
            {creating ? "Creating…" : "Create workload"}
          </button>
        </div>
      </Panel>

      <Panel title="Workload list" subtitle={`${workloads.length} workload(s)`}>
        {workloads.length === 0 ? (
          <EmptyState
            title="No workloads yet"
            description="Create a workload above to see it here."
          />
        ) : (
          <div className="stack-list">
            {workloads.map((w) => (
              <article key={w.workloadId} className="list-action" style={{ flexDirection: "column", alignItems: "flex-start", gap: 8 }}>
                <div className="list-action__title-row" style={{ width: "100%" }}>
                  <strong className="mono">{w.workloadId.slice(0, 8)}…</strong>
                  <StatusBadge status={w.state} tone={stateTone(w.state)} />
                </div>
                <p>{w.spec.image}{w.previewUrl ? ` → ${w.previewUrl}` : ""}</p>
                <div className="button-row">
                  {w.state === "created" ? (
                    <button
                      className="button button--primary"
                      type="button"
                      onClick={() => void handleStart(w.workloadId)}
                    >
                      Start
                    </button>
                  ) : null}
                  {w.state === "running" ? (
                    <button
                      className="button button--secondary"
                      type="button"
                      onClick={() => void handleStop(w.workloadId)}
                    >
                      Stop
                    </button>
                  ) : null}
                  <button
                    className="button button--secondary"
                    type="button"
                    onClick={() => void handleViewLogs(w.workloadId)}
                  >
                    {logsLoading ? "Loading…" : "Logs"}
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </Panel>

      {selectedLogs ? (
        <Panel
          title={`Logs — ${selectedLogs.workloadId.slice(0, 8)}…`}
          subtitle={`${selectedLogs.logs.length} line(s)`}
          actions={
            <button
              className="button button--secondary"
              type="button"
              onClick={() => setSelectedLogs(null)}
            >
              Close
            </button>
          }
        >
          <div
            ref={logsRef}
            style={{
              maxHeight: 320,
              overflowY: "auto",
              background: "var(--color-bg-inset)",
              padding: 12,
              borderRadius: 6,
            }}
          >
            {selectedLogs.logs.length === 0 ? (
              <p className="muted-text">No log output yet.</p>
            ) : (
              <pre className="mono" style={{ fontSize: "0.8rem", lineHeight: 1.6, whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
                {selectedLogs.logs.map((entry, idx) => (
                  <span key={idx}>{entry.line}{"\n"}</span>
                ))}
              </pre>
            )}
          </div>
        </Panel>
      ) : null}
    </div>
  );
}
