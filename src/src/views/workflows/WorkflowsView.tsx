import { useCallback, useEffect, useMemo, useState } from "react";
import type {
  WorkflowDefinition,
  WorkflowRun,
  WorkflowRunObservation,
} from "../../lib/api";
import {
  cancelWorkflowRun,
  createWorkflow,
  getWorkflowRun,
  listWorkflowRuns,
  listWorkflows,
  retryWorkflowRun,
  startWorkflowRun,
  validateWorkflow,
} from "../../lib/api";
import { getErrorMessage } from "../../lib/api";
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

const DEFAULT_DEFINITION = `{
  "name": "My workflow",
  "objective": "Describe what this workflow should accomplish",
  "steps": []
}`;

// Terminal run states never transition again, so polling/actions can stop.
const TERMINAL_RUN_STATES = new Set([
  "completed",
  "succeeded",
  "failed",
  "cancelled",
  "rejected",
  "budget_exceeded",
]);

function runStateTone(state: string) {
  const value = state.toLowerCase();
  if (["completed", "succeeded"].includes(value)) return "good" as const;
  if (["failed", "rejected", "budget_exceeded"].includes(value))
    return "bad" as const;
  if (["cancelled"].includes(value)) return "neutral" as const;
  return "warn" as const;
}

export function WorkflowsView() {
  const [workflows, setWorkflows] = useState<WorkflowDefinition[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Definition editor (JSON) + validation feedback.
  const [editorText, setEditorText] = useState<string>(DEFAULT_DEFINITION);
  const [problems, setProblems] = useState<unknown[] | null>(null);
  const [validationValid, setValidationValid] = useState<boolean | null>(null);
  const [validating, setValidating] = useState(false);
  const [creating, setCreating] = useState(false);

  // Selected workflow + its runs.
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string | null>(
    null,
  );
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [starting, setStarting] = useState(false);

  // Observed run (state + step states + history), refreshed from CP + events.
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [observation, setObservation] = useState<WorkflowRunObservation | null>(
    null,
  );
  const [actionBusy, setActionBusy] = useState(false);

  // Live event stream (shared hook). Drive run/step rendering from streamed
  // events (Req 4.1, 20.4) — no direct kernel/db access.
  const { events, status: streamStatus, eventsForRun } = useWorkflowEvents();

  const refreshWorkflows = useCallback(async () => {
    setLoading(true);
    try {
      const next = await listWorkflows();
      setWorkflows(next);
      setError(null);
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshWorkflows();
  }, [refreshWorkflows]);

  const refreshRuns = useCallback(async (workflowId: string) => {
    try {
      const next = await listWorkflowRuns(workflowId);
      setRuns(next);
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    }
  }, []);

  useEffect(() => {
    if (selectedWorkflowId) {
      void refreshRuns(selectedWorkflowId);
    } else {
      setRuns([]);
    }
  }, [selectedWorkflowId, refreshRuns]);

  const refreshObservation = useCallback(async (runId: string) => {
    try {
      const next = await getWorkflowRun(runId);
      setObservation(next);
      setError(null);
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    }
  }, []);

  useEffect(() => {
    if (selectedRunId) {
      void refreshObservation(selectedRunId);
    } else {
      setObservation(null);
    }
  }, [selectedRunId, refreshObservation]);

  // Whenever a new event lands for the observed run, re-fetch its authoritative
  // state from the Control_Plane so step states stay live.
  const runEventCount = selectedRunId
    ? events.filter((event) => event.run_id === selectedRunId).length
    : 0;
  useEffect(() => {
    if (selectedRunId && runEventCount > 0) {
      void refreshObservation(selectedRunId);
      if (selectedWorkflowId) {
        void refreshRuns(selectedWorkflowId);
      }
    }
    // Re-run when a new event arrives for the selected run.
  }, [
    runEventCount,
    selectedRunId,
    selectedWorkflowId,
    refreshObservation,
    refreshRuns,
  ]);

  const parsedDefinition = useMemo<{
    value: Record<string, unknown> | null;
    error: string | null;
  }>(() => {
    try {
      const value = JSON.parse(editorText) as unknown;
      if (!value || typeof value !== "object" || Array.isArray(value)) {
        return { value: null, error: "Definition must be a JSON object." };
      }
      return { value: value as Record<string, unknown>, error: null };
    } catch (err: unknown) {
      return { value: null, error: getErrorMessage(err) };
    }
  }, [editorText]);

  const handleSelectWorkflow = (workflow: WorkflowDefinition) => {
    setSelectedWorkflowId(workflow.id);
    setSelectedRunId(null);
    setEditorText(JSON.stringify(workflow.definition, null, 2));
    setProblems(null);
    setValidationValid(null);
  };

  const handleNewDefinition = () => {
    setSelectedWorkflowId(null);
    setSelectedRunId(null);
    setEditorText(DEFAULT_DEFINITION);
    setProblems(null);
    setValidationValid(null);
  };

  const handleValidate = async () => {
    if (!parsedDefinition.value) {
      setProblems([parsedDefinition.error ?? "Invalid JSON."]);
      setValidationValid(false);
      return;
    }
    setValidating(true);
    try {
      const result = await validateWorkflow(parsedDefinition.value);
      setValidationValid(result.valid);
      setProblems(result.problems ?? []);
      setError(null);
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      setValidating(false);
    }
  };

  const handleCreate = async () => {
    if (!parsedDefinition.value) {
      setProblems([parsedDefinition.error ?? "Invalid JSON."]);
      setValidationValid(false);
      return;
    }
    setCreating(true);
    try {
      const created = await createWorkflow(parsedDefinition.value);
      setProblems(null);
      setValidationValid(true);
      setError(null);
      await refreshWorkflows();
      setSelectedWorkflowId(created.id);
      setEditorText(JSON.stringify(created.definition, null, 2));
    } catch (err: unknown) {
      // The Control_Plane rejects invalid definitions with a 400 + reason.
      setError(getErrorMessage(err));
      setValidationValid(false);
    } finally {
      setCreating(false);
    }
  };

  const handleStartRun = async () => {
    if (!selectedWorkflowId) return;
    setStarting(true);
    try {
      const run = await startWorkflowRun(selectedWorkflowId);
      setError(null);
      await refreshRuns(selectedWorkflowId);
      setSelectedRunId(run.id);
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      setStarting(false);
    }
  };

  const handleCancel = async (runId: string) => {
    setActionBusy(true);
    try {
      await cancelWorkflowRun(runId);
      await refreshObservation(runId);
      if (selectedWorkflowId) await refreshRuns(selectedWorkflowId);
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      setActionBusy(false);
    }
  };

  const handleRetry = async (runId: string) => {
    setActionBusy(true);
    try {
      await retryWorkflowRun(runId);
      await refreshObservation(runId);
      if (selectedWorkflowId) await refreshRuns(selectedWorkflowId);
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      setActionBusy(false);
    }
  };

  const observedRun = observation?.run ?? null;
  const observedState = observedRun?.state ?? "";
  const isTerminal = TERMINAL_RUN_STATES.has(observedState.toLowerCase());
  const liveEvents = selectedRunId ? eventsForRun(selectedRunId) : [];
  // Prefer streamed history if richer than the last fetch, else the snapshot.
  const historyEvents =
    liveEvents.length >= (observation?.events.length ?? 0)
      ? liveEvents
      : (observation?.events ?? []);

  return (
    <div className="page-stack">
      <PageHeader
        title="Workflows"
        description="Create, validate, run, observe, cancel, and retry workflows. Driven entirely by Control_Plane HTTP + WebSocket APIs."
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
              onClick={() => void refreshWorkflows()}
              disabled={loading}
            >
              {loading ? "Refreshing…" : "Refresh"}
            </button>
          </div>
        }
      />

      {error ? (
        <InlineNotice tone="bad" title="Workflow error">
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
        title="Workflows"
        subtitle={`${workflows.length} definition(s)`}
        actions={
          <button
            className="button button--secondary"
            type="button"
            onClick={handleNewDefinition}
          >
            New definition
          </button>
        }
      >
        {workflows.length === 0 ? (
          <EmptyState
            title="No workflows yet"
            description="Define one in the editor below, validate it, then create it."
          />
        ) : (
          <div className="stack-list">
            {workflows.map((workflow) => (
              <article
                key={workflow.id}
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
                  <strong>{workflow.name || "(untitled)"}</strong>
                  {selectedWorkflowId === workflow.id ? (
                    <StatusBadge tone="accent" label="Selected" />
                  ) : null}
                </div>
                <p>{workflow.objective || "No objective set."}</p>
                <div className="button-row">
                  <button
                    className="button button--secondary"
                    type="button"
                    onClick={() => handleSelectWorkflow(workflow)}
                  >
                    Edit
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </Panel>

      <Panel
        title={selectedWorkflowId ? "Edit definition" : "Create definition"}
        subtitle="Edit the workflow JSON, validate against the Control_Plane planner, then create."
      >
        <div className="form-field">
          <label htmlFor="wf-editor">Definition (JSON)</label>
          <textarea
            id="wf-editor"
            value={editorText}
            onChange={(event) => {
              setEditorText(event.target.value);
              setValidationValid(null);
              setProblems(null);
            }}
            spellCheck={false}
            rows={16}
            style={{
              width: "100%",
              fontFamily: "var(--font-mono, monospace)",
              fontSize: "0.82rem",
              lineHeight: 1.5,
            }}
          />
        </div>

        {parsedDefinition.error ? (
          <InlineNotice tone="warn" title="Definition is not valid JSON">
            <p>{parsedDefinition.error}</p>
          </InlineNotice>
        ) : null}

        {validationValid === true ? (
          <InlineNotice tone="good" title="Definition is valid">
            <p>The Control_Plane planner accepted this definition.</p>
          </InlineNotice>
        ) : null}

        {problems && problems.length > 0 ? (
          <InlineNotice tone="bad" title={`${problems.length} problem(s) found`}>
            <JsonBlock value={problems} />
          </InlineNotice>
        ) : null}

        {validationValid === false &&
        (!problems || problems.length === 0) ? (
          <InlineNotice tone="bad" title="Definition was rejected">
            <p>See the error notice above for the cause.</p>
          </InlineNotice>
        ) : null}

        <div className="button-row" style={{ marginTop: 12 }}>
          <button
            className="button button--secondary"
            type="button"
            onClick={() => void handleValidate()}
            disabled={validating || !parsedDefinition.value}
          >
            {validating ? "Validating…" : "Validate"}
          </button>
          <button
            className="button button--primary"
            type="button"
            onClick={() => void handleCreate()}
            disabled={creating || !parsedDefinition.value}
          >
            {creating ? "Creating…" : "Create workflow"}
          </button>
          {selectedWorkflowId ? (
            <button
              className="button button--primary"
              type="button"
              onClick={() => void handleStartRun()}
              disabled={starting}
            >
              {starting ? "Starting…" : "Start run"}
            </button>
          ) : null}
        </div>
      </Panel>

      {selectedWorkflowId ? (
        <Panel title="Runs" subtitle={`${runs.length} run(s) for this workflow`}>
          {runs.length === 0 ? (
            <EmptyState
              title="No runs yet"
              description="Start a run from the editor above to observe it live."
            />
          ) : (
            <div className="stack-list">
              {runs.map((run) => (
                <article
                  key={run.id}
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
                    <strong className="mono">{run.id.slice(0, 8)}…</strong>
                    <StatusBadge
                      status={run.state}
                      tone={runStateTone(run.state)}
                    />
                  </div>
                  <p>Created {formatDateTime(run.created_at)}</p>
                  <div className="button-row">
                    <button
                      className="button button--secondary"
                      type="button"
                      onClick={() => setSelectedRunId(run.id)}
                    >
                      Observe
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </Panel>
      ) : null}

      {observedRun ? (
        <Panel
          title={`Run ${observedRun.id.slice(0, 8)}…`}
          subtitle="Live state, step states, and event history."
          actions={
            <div className="button-row">
              <StatusBadge
                status={observedRun.state}
                tone={runStateTone(observedRun.state)}
              />
              <button
                className="button button--secondary"
                type="button"
                onClick={() => void refreshObservation(observedRun.id)}
              >
                Refresh
              </button>
              {!isTerminal ? (
                <button
                  className="button button--secondary"
                  type="button"
                  onClick={() => void handleCancel(observedRun.id)}
                  disabled={actionBusy}
                >
                  {actionBusy ? "Working…" : "Cancel"}
                </button>
              ) : null}
              {["failed", "cancelled"].includes(
                observedRun.state.toLowerCase(),
              ) ? (
                <button
                  className="button button--primary"
                  type="button"
                  onClick={() => void handleRetry(observedRun.id)}
                  disabled={actionBusy}
                >
                  {actionBusy ? "Working…" : "Retry"}
                </button>
              ) : null}
            </div>
          }
        >
          <h3 style={{ marginTop: 0 }}>Steps</h3>
          {observation && observation.steps.length > 0 ? (
            <div className="stack-list">
              {observation.steps.map((step) => (
                <div
                  key={step.step_id}
                  className="list-action"
                  style={{ justifyContent: "space-between" }}
                >
                  <div>
                    <strong className="mono">{step.step_id}</strong>
                    <span style={{ marginLeft: 8, color: "var(--muted)" }}>
                      {step.step_type}
                    </span>
                    {step.error_message ? (
                      <p style={{ color: "var(--danger, #c00)" }}>
                        {step.error_message}
                      </p>
                    ) : null}
                  </div>
                  <StatusBadge status={step.state} />
                </div>
              ))}
            </div>
          ) : (
            <EmptyState
              title="No steps"
              description="This run has no recorded step states yet."
            />
          )}

          <h3>Event history</h3>
          {historyEvents.length === 0 ? (
            <EmptyState
              title="No events yet"
              description="Workflow events will stream in here as the run progresses."
            />
          ) : (
            <div
              style={{
                maxHeight: 320,
                overflowY: "auto",
                background: "var(--color-bg-inset)",
                padding: 12,
                borderRadius: 6,
              }}
            >
              <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
                {historyEvents.map((event) => (
                  <li
                    key={`${event.run_id}-${event.seq}`}
                    style={{
                      display: "flex",
                      gap: 8,
                      padding: "4px 0",
                      borderBottom: "1px solid var(--border, #2222)",
                    }}
                  >
                    <span className="mono" style={{ color: "var(--muted)" }}>
                      #{event.seq}
                    </span>
                    <span className="mono">{event.type}</span>
                    {event.step_id ? (
                      <span style={{ color: "var(--muted)" }}>
                        [{event.step_id}]
                      </span>
                    ) : null}
                    <span style={{ flex: 1 }}>{event.message}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Panel>
      ) : null}
    </div>
  );
}
