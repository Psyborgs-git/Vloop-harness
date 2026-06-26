import { useEffect, useMemo, useState } from "react";
import {
  getErrorMessage,
  getInvocation,
  getInvocationEvents,
  invokeAgent,
  isTerminalInvocationStatus,
  listInvocations,
  sortInvocations,
  type AgentConfig,
  type InvocationEvent,
  type InvocationRecord,
  type ProviderConfig,
} from "../../lib/api";
import {
  EmptyState,
  InlineNotice,
  PageHeader,
  Panel,
  StatusBadge,
} from "../../components/ui";
import { InputForm } from "./InputForm";
import {
  OverridesPanel,
  type PlaygroundOverridesState,
} from "./OverridesPanel";
import { InvocationDetails } from "./InvocationDetails";
import { RecentRuns } from "./RecentRuns";

interface PlaygroundViewProps {
  agents: AgentConfig[];
  providers: ProviderConfig[];
  invocations: InvocationRecord[];
  apiAvailable: boolean;
  warning: string | null;
  selectedAgentId: string | null;
  onSelectAgent: (agentId: string) => void;
  onInvocationSaved: (invocation: InvocationRecord) => void;
}

export function PlaygroundView({
  agents,
  providers,
  invocations,
  apiAvailable,
  warning,
  selectedAgentId,
  onSelectAgent,
  onInvocationSaved,
}: PlaygroundViewProps) {
  const selectedAgent =
    agents.find((agent) => agent.id === selectedAgentId) ?? agents[0] ?? null;
  const providerMap = useMemo(
    () => new Map(providers.map((provider) => [provider.id, provider])),
    [providers],
  );

  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [overrides, setOverrides] = useState<PlaygroundOverridesState>({
    providerId: "",
    model: "",
    temperature: "",
    maxTokens: "",
  });
  const [showValidation, setShowValidation] = useState(false);
  const [notice, setNotice] = useState<{
    tone: "good" | "warn" | "bad";
    title: string;
    description?: string;
  } | null>(null);
  const [recentRuns, setRecentRuns] = useState<InvocationRecord[]>([]);
  const [selectedInvocationId, setSelectedInvocationId] = useState<
    string | null
  >(null);
  const [currentInvocation, setCurrentInvocation] =
    useState<InvocationRecord | null>(null);
  const [currentEvents, setCurrentEvents] = useState<InvocationEvent[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [isRefreshingRuns, setIsRefreshingRuns] = useState(false);

  const requiredErrors = validateInputs(selectedAgent, inputs);

  useEffect(() => {
    if (!selectedAgent) {
      setInputs({});
      setOverrides({
        providerId: "",
        model: "",
        temperature: "",
        maxTokens: "",
      });
      return;
    }

    onSelectAgent(selectedAgent.id);
    setInputs((current) => {
      const next: Record<string, string> = {};
      selectedAgent.inputFields.forEach((field) => {
        next[field.name] = current[field.name] ?? "";
      });
      return next;
    });
    setOverrides((current) => ({
      providerId:
        current.providerId &&
        providers.some((provider) => provider.id === current.providerId)
          ? current.providerId
          : selectedAgent.defaultProviderId,
      model: "",
      temperature: "",
      maxTokens: "",
    }));
  }, [onSelectAgent, providers, selectedAgent]);

  useEffect(() => {
    const fallbackRuns = sortInvocations(
      invocations.filter((invocation) =>
        selectedAgent ? invocation.agentId === selectedAgent.id : true,
      ),
    );
    setRecentRuns(fallbackRuns);
  }, [invocations, selectedAgent]);

  useEffect(() => {
    if (!apiAvailable) {
      return;
    }

    let cancelled = false;
    setIsRefreshingRuns(true);
    void listInvocations(selectedAgent?.id)
      .then((runs) => {
        if (!cancelled) {
          setRecentRuns(runs);
        }
      })
      .catch(() => {
        // Fall back to the latest bootstrap-sourced list.
      })
      .finally(() => {
        if (!cancelled) {
          setIsRefreshingRuns(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [apiAvailable, selectedAgent?.id]);

  useEffect(() => {
    if (!selectedInvocationId || !apiAvailable) {
      return;
    }

    let cancelled = false;
    void loadInvocationDetails(selectedInvocationId, {
      onInvocationSaved,
      onInvocationLoaded: (invocation, events) => {
        if (cancelled) {
          return;
        }
        setCurrentInvocation(invocation);
        setCurrentEvents(events);
        setRecentRuns((current) => upsertInvocation(current, invocation));
      },
    }).catch((error) => {
      if (!cancelled) {
        setNotice({
          tone: "bad",
          title: "Could not load invocation details",
          description: getErrorMessage(error),
        });
      }
    });

    return () => {
      cancelled = true;
    };
  }, [apiAvailable, onInvocationSaved, selectedInvocationId]);

  useEffect(() => {
    if (
      !currentInvocation?.id ||
      isTerminalInvocationStatus(currentInvocation.status) ||
      !apiAvailable
    ) {
      setIsRunning(false);
      return;
    }

    setIsRunning(true);
    const timer = window.setInterval(() => {
      void loadInvocationDetails(currentInvocation.id, {
        onInvocationSaved,
        onInvocationLoaded: (invocation, events) => {
          setCurrentInvocation(invocation);
          setCurrentEvents(events);
          setRecentRuns((current) => upsertInvocation(current, invocation));
          if (isTerminalInvocationStatus(invocation.status)) {
            setIsRunning(false);
          }
        },
      }).catch((error) => {
        setNotice({
          tone: "bad",
          title: "Invocation polling failed",
          description: getErrorMessage(error),
        });
        setIsRunning(false);
      });
    }, 1500);

    return () => {
      window.clearInterval(timer);
    };
  }, [
    apiAvailable,
    currentInvocation?.id,
    currentInvocation?.status,
    onInvocationSaved,
  ]);

  async function handleRunAgent() {
    if (!selectedAgent) {
      return;
    }

    setShowValidation(true);
    if (Object.keys(requiredErrors).length > 0) {
      setNotice({
        tone: "bad",
        title: "Required inputs are missing",
        description: "Fill the highlighted fields before starting a run.",
      });
      return;
    }

    if (!apiAvailable) {
      setNotice({
        tone: "warn",
        title: "Playground APIs unavailable",
        description:
          "This Control Plane build does not expose the /api/v1 invocation routes yet.",
      });
      return;
    }

    const invocationInputs = Object.fromEntries(
      selectedAgent.inputFields.map((field) => [
        field.name,
        inputs[field.name] ?? "",
      ]),
    );

    const invocationOverrides: Record<string, string | number> = {};
    if (
      overrides.providerId &&
      overrides.providerId !== selectedAgent.defaultProviderId
    ) {
      invocationOverrides.providerId = overrides.providerId;
    }
    if (overrides.model.trim()) {
      invocationOverrides.model = overrides.model.trim();
    }
    if (overrides.temperature.trim()) {
      invocationOverrides.temperature = Number(overrides.temperature);
    }
    if (overrides.maxTokens.trim()) {
      invocationOverrides.maxTokens = Number(overrides.maxTokens);
    }

    try {
      const invocation = await invokeAgent(selectedAgent.id, {
        inputs: invocationInputs,
        overrides: invocationOverrides,
      });
      setSelectedInvocationId(invocation.id);
      setCurrentInvocation(invocation);
      setCurrentEvents([]);
      setRecentRuns((current) => upsertInvocation(current, invocation));
      onInvocationSaved(invocation);
      setNotice({
        tone: "good",
        title: "Invocation started",
        description:
          "Polling will continue until the run reaches a terminal status.",
      });
      setIsRunning(true);
    } catch (error) {
      setNotice({
        tone: "bad",
        title: "Could not start invocation",
        description: getErrorMessage(error),
      });
    }
  }

  function handleSelectRecentRun(invocation: InvocationRecord) {
    if (invocation.agentId !== selectedAgent?.id) {
      onSelectAgent(invocation.agentId);
    }
    setSelectedInvocationId(invocation.id);
    setCurrentInvocation(invocation);
  }

  function handleChangeInput(fieldName: string, value: string) {
    setInputs((current) => ({ ...current, [fieldName]: value }));
  }

  function handleChangeOverrides<K extends keyof PlaygroundOverridesState>(
    key: K,
    value: PlaygroundOverridesState[K],
  ) {
    setOverrides((current) => ({ ...current, [key]: value }));
  }

  const selectedProvider = providerMap.get(
    overrides.providerId || selectedAgent?.defaultProviderId || "",
  );
  const canRun = Boolean(selectedAgent) && !isRunning;

  return (
    <div className="page-stack">
      <PageHeader
        title="Playground"
        description="Run an agent against live provider settings, inspect its invocation timeline, and compare recent outputs."
        actions={
          <div className="button-row">
            <button
              className="button button--secondary"
              type="button"
              onClick={() => {
                if (!apiAvailable) {
                  return;
                }
                setIsRefreshingRuns(true);
                void listInvocations(selectedAgent?.id)
                  .then((runs) => setRecentRuns(runs))
                  .catch((error) => {
                    setNotice({
                      tone: "bad",
                      title: "Could not refresh recent runs",
                      description: getErrorMessage(error),
                    });
                  })
                  .finally(() => setIsRefreshingRuns(false));
              }}
              disabled={!apiAvailable || isRefreshingRuns}
            >
              {isRefreshingRuns ? "Refreshing…" : "Refresh runs"}
            </button>
          </div>
        }
      />

      {warning ? (
        <InlineNotice
          tone={apiAvailable ? "warn" : "bad"}
          title={
            apiAvailable
              ? "Bootstrap fallback in use"
              : "Playground APIs unavailable"
          }
        >
          <p>{warning}</p>
        </InlineNotice>
      ) : null}

      {!selectedAgent ? (
        <EmptyState
          title="No agent available"
          description="Create and save an agent first, then return here to render its dynamic input form and run it end to end."
        />
      ) : (
        <>
          {notice ? (
            <InlineNotice tone={notice.tone} title={notice.title}>
              {notice.description ? <p>{notice.description}</p> : null}
            </InlineNotice>
          ) : null}

          <div className="page-grid page-grid--playground">
            <Panel
              title="Invocation setup"
              subtitle="Agent selection, dynamic inputs, and optional runtime overrides."
            >
              <div className="form-grid form-grid--two">
                <label className="field">
                  <span className="field__label">Agent</span>
                  <select
                    className="select"
                    value={selectedAgent.id}
                    onChange={(event) => onSelectAgent(event.target.value)}
                  >
                    {agents.map((agent) => (
                      <option key={agent.id} value={agent.id}>
                        {agent.name}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="hint-card">
                  <strong>{selectedAgent.name}</strong>
                  <p>
                    {selectedAgent.description || "No description provided."}
                  </p>
                  <div className="hint-card__meta">
                    <span>
                      Provider:{" "}
                      {providerMap.get(selectedAgent.defaultProviderId)?.name ??
                        "Missing provider"}
                    </span>
                    <span>Output: {selectedAgent.outputMode}</span>
                    <span>Reasoning: {selectedAgent.reasoningMode}</span>
                  </div>
                </div>
              </div>

              <InputForm
                agent={selectedAgent}
                inputs={inputs}
                showValidation={showValidation}
                requiredErrors={requiredErrors}
                providerMap={providerMap}
                onChangeInput={handleChangeInput}
              />

              <OverridesPanel
                agent={selectedAgent}
                providers={providers}
                overrides={overrides}
                selectedProvider={selectedProvider}
                onChangeOverrides={handleChangeOverrides}
              />

              <div className="editor-footer">
                <div className="editor-footer__meta">
                  <StatusBadge
                    status={selectedAgent.enabled ? "enabled" : "disabled"}
                    label={selectedAgent.enabled ? "Enabled" : "Disabled"}
                  />
                  <span>
                    Default provider{" "}
                    {providerMap.get(selectedAgent.defaultProviderId)?.name ??
                      "missing"}
                  </span>
                </div>
                <div className="button-row">
                  <button
                    className="button button--primary"
                    type="button"
                    onClick={() => {
                      void handleRunAgent();
                    }}
                    disabled={!canRun}
                  >
                    {isRunning ? "Running…" : "Run agent"}
                  </button>
                </div>
              </div>
            </Panel>

            <Panel
              title="Invocation output"
              subtitle="Terminal status, provider resolution, reasoning, parsed JSON, and event timeline."
            >
              <InvocationDetails
                invocation={currentInvocation}
                events={currentEvents}
                providerMap={providerMap}
              />
            </Panel>
          </div>

          <Panel
            title="Recent runs"
            subtitle="The latest runs for the selected agent. Click one to inspect it in place."
          >
            <RecentRuns
              invocations={recentRuns}
              selectedInvocationId={selectedInvocationId}
              providerMap={providerMap}
              onSelect={handleSelectRecentRun}
            />
          </Panel>
        </>
      )}
    </div>
  );
}

/* ─────── Internal helpers ─────── */

async function loadInvocationDetails(
  invocationId: string,
  options: {
    onInvocationSaved: (invocation: InvocationRecord) => void;
    onInvocationLoaded: (
      invocation: InvocationRecord,
      events: InvocationEvent[],
    ) => void;
  },
) {
  const [invocation, events] = await Promise.all([
    getInvocation(invocationId),
    getInvocationEvents(invocationId),
  ]);
  options.onInvocationSaved(invocation);
  options.onInvocationLoaded(invocation, events);
}

function validateInputs(
  agent: AgentConfig | null,
  inputs: Record<string, string>,
): Record<string, string> {
  if (!agent) {
    return {};
  }

  return Object.fromEntries(
    agent.inputFields
      .filter((field) => field.required && !(inputs[field.name] ?? "").trim())
      .map((field) => [field.name, `${field.label} is required.`]),
  );
}

function upsertInvocation(
  current: InvocationRecord[],
  invocation: InvocationRecord,
): InvocationRecord[] {
  const next = current.filter((entry) => entry.id !== invocation.id);
  next.unshift(invocation);
  return sortInvocations(next).slice(0, 50);
}
