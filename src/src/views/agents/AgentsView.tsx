import { useEffect, useMemo, useState } from "react";
import {
  deleteAgent,
  getErrorMessage,
  saveAgent,
  validateAgent,
  type AgentConfig,
  type AgentMutationPayload,
  type AgentTemplate,
  type ProviderConfig,
} from "../../lib/api";
import { InlineNotice, PageHeader, Panel } from "../../components/ui";
import type { AgentFormState } from "./AgentFormTypes";
import {
  agentToForm,
  createDraft,
  emptyToNull,
  humanize,
  serializeForm,
  slugify,
  validateAgentForm,
} from "./AgentFormHelpers";
import { AgentList } from "./AgentList";
import { AgentForm } from "./AgentForm";

interface AgentsViewProps {
  agents: AgentConfig[];
  providers: ProviderConfig[];
  agentTemplates: AgentTemplate[];
  apiAvailable: boolean;
  warning: string | null;
  onAgentSaved: (agent: AgentConfig) => void;
  onAgentDeleted: (agentId: string) => void;
  onOpenPlayground: (agentId: string) => void;
}

export function AgentsView({
  agents,
  providers,
  agentTemplates,
  apiAvailable,
  warning,
  onAgentSaved,
  onAgentDeleted,
  onOpenPlayground,
}: AgentsViewProps) {
  const providerMap = useMemo(
    () => new Map(providers.map((provider) => [provider.id, provider])),
    [providers],
  );

  const [selectedId, setSelectedId] = useState<string | "new">(
    agents[0]?.id ?? "new",
  );
  const [form, setForm] = useState<AgentFormState>(() =>
    agents[0]
      ? agentToForm(agents[0], providers[0]?.id ?? "")
      : createDraft(providers[0]?.id ?? ""),
  );
  const [baseline, setBaseline] = useState<string>(() => serializeForm(form));
  const [templateId, setTemplateId] = useState(agentTemplates[0]?.id ?? "");
  const [slugEdited, setSlugEdited] = useState(false);
  const [showValidation, setShowValidation] = useState(false);
  const [notice, setNotice] = useState<{
    tone: "good" | "warn" | "bad";
    title: string;
    description?: string;
  } | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isValidating, setIsValidating] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const validation = validateAgentForm(form, providers);
  const isDirty = serializeForm(form) !== baseline;

  useEffect(() => {
    if (selectedId === "new") {
      if (
        !form.id &&
        !isDirty &&
        form.defaultProviderId !== (providers[0]?.id ?? "")
      ) {
        const nextForm = { ...form, defaultProviderId: providers[0]?.id ?? "" };
        setForm(nextForm);
        setBaseline(serializeForm(nextForm));
      }
      return;
    }

    const selectedAgent = agents.find((agent) => agent.id === selectedId);
    if (selectedAgent) {
      if (!isDirty) {
        const nextForm = agentToForm(selectedAgent, providers[0]?.id ?? "");
        setForm(nextForm);
        setBaseline(serializeForm(nextForm));
      }
      return;
    }

    if (agents[0]) {
      const nextForm = agentToForm(agents[0], providers[0]?.id ?? "");
      setSelectedId(agents[0].id);
      setForm(nextForm);
      setBaseline(serializeForm(nextForm));
    } else {
      const nextForm = createDraft(providers[0]?.id ?? "");
      setSelectedId("new");
      setForm(nextForm);
      setBaseline(serializeForm(nextForm));
    }
  }, [agents, form, isDirty, providers, selectedId]);

  useEffect(() => {
    if (!templateId && agentTemplates[0]) {
      setTemplateId(agentTemplates[0].id);
    }
  }, [agentTemplates, templateId]);

  function selectAgent(agent: AgentConfig) {
    const nextForm = agentToForm(agent, providers[0]?.id ?? "");
    setSelectedId(agent.id);
    setForm(nextForm);
    setBaseline(serializeForm(nextForm));
    setSlugEdited(true);
    setShowValidation(false);
    setNotice(null);
    setConfirmDelete(false);
  }

  function startNewAgent() {
    const nextForm = createDraft(providers[0]?.id ?? "");
    setSelectedId("new");
    setForm(nextForm);
    setBaseline(serializeForm(nextForm));
    setSlugEdited(false);
    setShowValidation(false);
    setNotice(null);
    setConfirmDelete(false);
  }

  function updateField<K extends keyof AgentFormState>(
    key: K,
    value: AgentFormState[K],
  ) {
    setForm((current) => ({ ...current, [key]: value }));
    setConfirmDelete(false);
  }

  function updateName(value: string) {
    setForm((current) => ({
      ...current,
      name: value,
      slug: slugEdited ? current.slug : slugify(value),
    }));
    setConfirmDelete(false);
  }

  function updateSlug(value: string) {
    setSlugEdited(true);
    updateField("slug", value);
  }

  function updateFieldRow(
    fieldId: string,
    patch: Partial<Omit<AgentFormState["inputFields"][number], "id">>,
  ) {
    setForm((current) => ({
      ...current,
      inputFields: current.inputFields.map((field) =>
        field.id === fieldId ? { ...field, ...patch } : field,
      ),
    }));
    setConfirmDelete(false);
  }

  function addInputField() {
    setForm((current) => ({
      ...current,
      inputFields: [
        ...current.inputFields,
        {
          id: `field-${Math.random().toString(36).slice(2, 10)}`,
          name: "",
          label: "",
          description: "",
          required: true,
        },
      ],
    }));
  }

  function removeInputField(fieldId: string) {
    setForm((current) => ({
      ...current,
      inputFields: current.inputFields.filter((field) => field.id !== fieldId),
    }));
  }

  function applyTemplate() {
    const template = agentTemplates.find((entry) => entry.id === templateId);
    if (!template) {
      return;
    }

    const nextForm: AgentFormState = {
      id: null,
      name: template.name,
      slug: slugify(template.name),
      description: template.description,
      instructions: template.instructions,
      reasoningMode:
        template.reasoningMode === "chain_of_thought"
          ? "chain_of_thought"
          : "predict",
      inputFields: template.inputFields.map((field) => ({
        ...field,
        id: `field-${Math.random().toString(36).slice(2, 10)}`,
        description: field.description ?? "",
      })),
      outputMode: template.outputMode === "json" ? "json" : "text",
      outputFieldName: template.outputFieldName,
      outputSchemaText: template.outputSchema
        ? JSON.stringify(template.outputSchema, null, 2)
        : "",
      defaultProviderId: form.defaultProviderId || providers[0]?.id || "",
      modelOverride: "",
      temperature: String(template.temperature),
      maxTokens: String(template.maxTokens),
      enabled: true,
      revision: 0,
      createdAt: "",
      updatedAt: "",
    };

    setSelectedId("new");
    setForm(nextForm);
    setBaseline(serializeForm(nextForm));
    setSlugEdited(false);
    setShowValidation(false);
    setNotice({
      tone: "good",
      title: "Template applied",
      description: `${template.name} has been loaded into the editor as a new draft.`,
    });
    setConfirmDelete(false);
  }

  function updateOutputMode(outputMode: "text" | "json") {
    setForm((current) => ({
      ...current,
      outputMode,
      outputSchemaText:
        outputMode === "json"
          ? current.outputSchemaText.trim() || '{\n  "response": "string"\n}'
          : "",
    }));
  }

  function buildPayload(): AgentMutationPayload | null {
    if (
      validation.formError ||
      Object.keys(validation.fieldErrors).length > 0
    ) {
      return null;
    }

    return {
      name: form.name.trim(),
      slug: form.slug.trim(),
      description: emptyToNull(form.description),
      instructions: form.instructions.trim(),
      reasoningMode: form.reasoningMode,
      inputFields: form.inputFields.map((field) => ({
        name: field.name.trim(),
        label:
          field.label.trim() ||
          humanize(field.name.trim()) ||
          field.name.trim(),
        description: emptyToNull(field.description),
        required: field.required,
      })),
      outputMode: form.outputMode,
      outputFieldName: form.outputFieldName.trim(),
      outputSchema: validation.parsedOutputSchema,
      defaultProviderId: form.defaultProviderId,
      modelOverride: emptyToNull(form.modelOverride),
      temperature: Number(form.temperature),
      maxTokens: Number(form.maxTokens),
      enabled: form.enabled,
    };
  }

  async function handleValidateAgent() {
    setShowValidation(true);
    const payload = buildPayload();
    if (!payload) {
      setNotice({
        tone: "bad",
        title: "Agent settings need attention",
        description:
          validation.formError ??
          "Fix the highlighted fields before validating.",
      });
      return;
    }

    if (!apiAvailable) {
      setNotice({
        tone: "warn",
        title: "Server validation unavailable",
        description:
          "Local validation passed, but this Control Plane build does not expose the /api/v1 agent validation routes yet.",
      });
      return;
    }

    setIsValidating(true);
    try {
      const result = await validateAgent(payload, form.id ?? undefined);
      setNotice({
        tone: result.valid ? "good" : "warn",
        title: result.valid
          ? "Validation passed"
          : "Validation returned warnings",
        description: result.normalized
          ? `${result.normalized.name} is ready to save.`
          : "The Control Plane accepted the payload shape.",
      });
    } catch (error) {
      setNotice({
        tone: "bad",
        title: "Could not validate agent",
        description: getErrorMessage(error),
      });
    } finally {
      setIsValidating(false);
    }
  }

  async function handleSaveAgent() {
    setShowValidation(true);
    const payload = buildPayload();
    if (!payload) {
      setNotice({
        tone: "bad",
        title: "Agent settings need attention",
        description:
          validation.formError ?? "Fix the highlighted fields before saving.",
      });
      return;
    }

    setIsSaving(true);
    try {
      const saved = await saveAgent(payload, form.id ?? undefined);
      const nextForm = agentToForm(saved, providers[0]?.id ?? "");
      setSelectedId(saved.id);
      setForm(nextForm);
      setBaseline(serializeForm(nextForm));
      setSlugEdited(true);
      setShowValidation(false);
      setNotice({
        tone: "good",
        title: form.id ? "Agent updated" : "Agent created",
        description: `${saved.name} is ready to run in the playground.`,
      });
      onAgentSaved(saved);
    } catch (error) {
      setNotice({
        tone: "bad",
        title: "Could not save agent",
        description: getErrorMessage(error),
      });
    } finally {
      setIsSaving(false);
    }
  }

  async function handleDeleteAgent() {
    if (!form.id) {
      startNewAgent();
      return;
    }

    if (!confirmDelete) {
      setConfirmDelete(true);
      return;
    }

    try {
      await deleteAgent(form.id);
      onAgentDeleted(form.id);
      const remaining = agents.filter((agent) => agent.id !== form.id);
      if (remaining[0]) {
        selectAgent(remaining[0]);
      } else {
        startNewAgent();
      }
      setNotice({
        tone: "good",
        title: "Agent deleted",
        description:
          "Any existing invocation history remains available in the playground recent-runs list.",
      });
    } catch (error) {
      setNotice({
        tone: "bad",
        title: "Could not delete agent",
        description: getErrorMessage(error),
      });
    } finally {
      setConfirmDelete(false);
    }
  }

  const canEdit = providers.length > 0;
  const canSubmit = apiAvailable && canEdit && !isSaving && !isValidating;

  return (
    <div className="page-stack">
      <PageHeader
        title="Agents"
        description="Define prompts, structured inputs, output shapes, and provider defaults for repeatable local agent runs."
        actions={
          <div className="button-row">
            {form.id ? (
              <button
                className="button button--secondary"
                type="button"
                onClick={() => onOpenPlayground(form.id!)}
              >
                Open in playground
              </button>
            ) : null}
            <button
              className="button button--secondary"
              type="button"
              onClick={startNewAgent}
            >
              New agent
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
              : "Agent APIs unavailable"
          }
        >
          <p>{warning}</p>
        </InlineNotice>
      ) : null}

      {!canEdit ? (
        <InlineNotice tone="warn" title="A provider is required first">
          <p>
            Create at least one provider before saving agents. The backend
            validates <code>defaultProviderId</code> against the current
            provider list.
          </p>
        </InlineNotice>
      ) : null}

      <div className="page-grid page-grid--sidebar">
        <Panel
          title={`Saved agents (${agents.length})`}
          subtitle="Each agent captures instructions, inputs, output rules, and default provider routing."
        >
          <AgentList
            agents={agents}
            providers={providers}
            selectedId={selectedId}
            onSelect={selectAgent}
            onStartNew={startNewAgent}
          />
        </Panel>

        <Panel
          title={form.id ? "Edit agent" : "New agent"}
          subtitle="Agents are validated against provider IDs, input-field identifiers, output modes, and JSON schema requirements."
        >
          <AgentForm
            form={form}
            providers={providers}
            agentTemplates={agentTemplates}
            apiAvailable={apiAvailable}
            templateId={templateId}
            showValidation={showValidation}
            validation={validation}
            isSaving={isSaving}
            isValidating={isValidating}
            canSubmit={canSubmit}
            confirmDelete={confirmDelete}
            notice={notice}
            onTemplateChange={setTemplateId}
            onApplyTemplate={applyTemplate}
            onUpdateField={updateField}
            onUpdateName={updateName}
            onUpdateSlug={updateSlug}
            onUpdateFieldRow={updateFieldRow}
            onAddInputField={addInputField}
            onRemoveInputField={removeInputField}
            onUpdateOutputMode={updateOutputMode}
            onValidate={handleValidateAgent}
            onSave={handleSaveAgent}
            onDelete={handleDeleteAgent}
          />
        </Panel>
      </div>
    </div>
  );
}
