import { useCallback, useEffect, useState } from "react";
import type { ScheduledTask, ScheduledTaskState } from "../../lib/api";
import {
  createScheduledTask,
  getErrorMessage,
  listScheduledTasks,
  pauseScheduledTask,
  resumeScheduledTask,
} from "../../lib/api";
import {
  EmptyState,
  InlineNotice,
  KeyValueList,
  PageHeader,
  Panel,
  StatusBadge,
  formatDateTime,
} from "../../components/ui";

// A Scheduled_Task's state maps to a badge tone. Everything here is driven
// entirely by the Control_Plane HTTP API (Req 20.4, 14.1) — no direct Scheduler
// or db access from the Frontend.
function scheduleStateTone(state: string) {
  const value = state.toLowerCase();
  if (value === "active") return "good" as const;
  if (value === "paused") return "warn" as const;
  return "neutral" as const;
}

export function ScheduleView() {
  const [tasks, setTasks] = useState<ScheduledTask[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Optional filter by workflow definition id.
  const [filterDefinitionId, setFilterDefinitionId] = useState("");
  const [activeFilter, setActiveFilter] = useState<string | null>(null);

  // Create form.
  const [formDefinitionId, setFormDefinitionId] = useState("");
  const [formCron, setFormCron] = useState("");
  const [formState, setFormState] = useState<ScheduledTaskState>("active");
  const [creating, setCreating] = useState(false);

  // Per-task in-flight pause/resume, keyed by task id.
  const [busyId, setBusyId] = useState<string | null>(null);

  const refreshTasks = useCallback(async (definitionId: string | null) => {
    setLoading(true);
    try {
      const next = await listScheduledTasks(definitionId ?? undefined);
      setTasks(next);
      setError(null);
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshTasks(activeFilter);
  }, [activeFilter, refreshTasks]);

  const handleApplyFilter = () => {
    const value = filterDefinitionId.trim();
    setActiveFilter(value ? value : null);
  };

  const handleClearFilter = () => {
    setFilterDefinitionId("");
    setActiveFilter(null);
  };

  const handleCreate = async () => {
    const definitionId = formDefinitionId.trim();
    const cronExpression = formCron.trim();
    if (!definitionId || !cronExpression) {
      return;
    }
    setCreating(true);
    try {
      await createScheduledTask({
        definitionId,
        cronExpression,
        state: formState,
      });
      setError(null);
      setFormCron("");
      await refreshTasks(activeFilter);
    } catch (err: unknown) {
      // The Control_Plane rejects an invalid cron expression with a 400 whose
      // message we surface here (Req 14.5).
      setError(getErrorMessage(err));
    } finally {
      setCreating(false);
    }
  };

  const handlePause = async (task: ScheduledTask) => {
    setBusyId(task.id);
    try {
      await pauseScheduledTask(task.id);
      setError(null);
      await refreshTasks(activeFilter);
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      setBusyId(null);
    }
  };

  const handleResume = async (task: ScheduledTask) => {
    setBusyId(task.id);
    try {
      await resumeScheduledTask(task.id);
      setError(null);
      await refreshTasks(activeFilter);
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      setBusyId(null);
    }
  };

  const canCreate =
    !creating && formDefinitionId.trim() !== "" && formCron.trim() !== "";

  return (
    <div className="page-stack">
      <PageHeader
        title="Schedule"
        description="Create, pause, and resume scheduled workflow tasks on a cron cadence. Driven entirely by Control_Plane HTTP APIs."
        actions={
          <div className="button-row">
            <button
              className="button button--secondary"
              type="button"
              onClick={() => void refreshTasks(activeFilter)}
              disabled={loading}
            >
              {loading ? "Refreshing…" : "Refresh"}
            </button>
          </div>
        }
      />

      {error ? (
        <InlineNotice tone="bad" title="Schedule error">
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
        title="Create scheduled task"
        subtitle="Trigger runs of a workflow definition on a cron cadence. Invalid cron expressions are rejected by the Control_Plane."
      >
        <div className="form-field">
          <label htmlFor="schedule-definition-id">Workflow definition id</label>
          <input
            id="schedule-definition-id"
            type="text"
            value={formDefinitionId}
            onChange={(event) => setFormDefinitionId(event.target.value)}
            placeholder="workflow definition id"
            spellCheck={false}
            style={{ width: "100%", fontFamily: "var(--font-mono, monospace)" }}
          />
        </div>

        <div className="form-field">
          <label htmlFor="schedule-cron">Cron expression</label>
          <input
            id="schedule-cron"
            type="text"
            value={formCron}
            onChange={(event) => setFormCron(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && canCreate) {
                event.preventDefault();
                void handleCreate();
              }
            }}
            placeholder="e.g. 0 9 * * * (minute hour day month weekday)"
            spellCheck={false}
            style={{ width: "100%", fontFamily: "var(--font-mono, monospace)" }}
          />
        </div>

        <div className="form-field">
          <label htmlFor="schedule-state">Initial state</label>
          <select
            id="schedule-state"
            value={formState}
            onChange={(event) =>
              setFormState(event.target.value as ScheduledTaskState)
            }
            style={{ width: "100%" }}
          >
            <option value="active">Active</option>
            <option value="paused">Paused</option>
          </select>
        </div>

        <div className="button-row" style={{ marginTop: 12 }}>
          <button
            className="button button--primary"
            type="button"
            onClick={() => void handleCreate()}
            disabled={!canCreate}
          >
            {creating ? "Creating…" : "Create scheduled task"}
          </button>
        </div>
      </Panel>

      <Panel
        title="Scheduled tasks"
        subtitle={`${tasks.length} scheduled task(s)${
          activeFilter ? ` for definition ${activeFilter}` : ""
        }`}
        actions={
          <div className="button-row" style={{ alignItems: "flex-end" }}>
            <div className="form-field" style={{ marginBottom: 0 }}>
              <label htmlFor="schedule-filter">Filter by definition id</label>
              <input
                id="schedule-filter"
                type="text"
                value={filterDefinitionId}
                onChange={(event) => setFilterDefinitionId(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    handleApplyFilter();
                  }
                }}
                placeholder="workflow definition id"
                spellCheck={false}
                style={{ fontFamily: "var(--font-mono, monospace)" }}
              />
            </div>
            <button
              className="button button--secondary"
              type="button"
              onClick={handleApplyFilter}
            >
              Apply
            </button>
            {activeFilter ? (
              <button
                className="button button--secondary"
                type="button"
                onClick={handleClearFilter}
              >
                Clear
              </button>
            ) : null}
          </div>
        }
      >
        {tasks.length === 0 ? (
          <EmptyState
            title="No scheduled tasks"
            description="Create one above to trigger a workflow definition on a cron cadence."
          />
        ) : (
          <div className="stack-list">
            {tasks.map((task) => {
              const busy = busyId === task.id;
              const isActive = task.state.toLowerCase() === "active";
              return (
                <article
                  key={task.id}
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
                    <strong className="mono">{task.id.slice(0, 8)}…</strong>
                    <StatusBadge
                      status={task.state}
                      tone={scheduleStateTone(task.state)}
                    />
                  </div>

                  <KeyValueList
                    items={[
                      {
                        label: "Definition",
                        value: (
                          <span className="mono">{task.definition_id}</span>
                        ),
                      },
                      {
                        label: "Cron",
                        value: (
                          <span className="mono">{task.cron_expression}</span>
                        ),
                      },
                      {
                        label: "Next run",
                        value: task.next_run_at
                          ? formatDateTime(task.next_run_at)
                          : "—",
                      },
                      {
                        label: "Created",
                        value: formatDateTime(task.created_at),
                      },
                    ]}
                  />

                  <div className="button-row">
                    {isActive ? (
                      <button
                        className="button button--secondary"
                        type="button"
                        onClick={() => void handlePause(task)}
                        disabled={busy}
                      >
                        {busy ? "Pausing…" : "Pause"}
                      </button>
                    ) : (
                      <button
                        className="button button--primary"
                        type="button"
                        onClick={() => void handleResume(task)}
                        disabled={busy}
                      >
                        {busy ? "Resuming…" : "Resume"}
                      </button>
                    )}
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
