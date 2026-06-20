import { useEffect, useMemo, useState } from 'react';
import {
  deleteAgent,
  getErrorMessage,
  saveAgent,
  validateAgent,
  type AgentConfig,
  type AgentInputField,
  type AgentMutationPayload,
  type AgentTemplate,
  type ProviderConfig,
} from '../lib/api';
import {
  EmptyState,
  InlineNotice,
  JsonBlock,
  PageHeader,
  Panel,
  StatusBadge,
  cx,
  formatDateTime,
  formatRelativeTime,
} from '../components/ui';

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

interface AgentFieldState extends AgentInputField {
  id: string;
}

interface AgentFormState {
  id: string | null;
  name: string;
  slug: string;
  description: string;
  instructions: string;
  reasoningMode: 'predict' | 'chain_of_thought';
  inputFields: AgentFieldState[];
  outputMode: 'text' | 'json';
  outputFieldName: string;
  outputSchemaText: string;
  defaultProviderId: string;
  modelOverride: string;
  temperature: string;
  maxTokens: string;
  enabled: boolean;
  revision: number;
  createdAt: string;
  updatedAt: string;
}

interface AgentValidationState {
  fieldErrors: Partial<
    Record<
      | 'name'
      | 'slug'
      | 'instructions'
      | 'outputFieldName'
      | 'outputSchemaText'
      | 'defaultProviderId'
      | 'temperature'
      | 'maxTokens'
      | `field-name-${string}`
      | `field-label-${string}`,
      string
    >
  >;
  formError: string | null;
  parsedOutputSchema: Record<string, unknown> | null;
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

  const [selectedId, setSelectedId] = useState<string | 'new'>(agents[0]?.id ?? 'new');
  const [form, setForm] = useState<AgentFormState>(() =>
    agents[0] ? agentToForm(agents[0], providers[0]?.id ?? '') : createDraft(providers[0]?.id ?? ''),
  );
  const [baseline, setBaseline] = useState<string>(() => serializeForm(form));
  const [templateId, setTemplateId] = useState(agentTemplates[0]?.id ?? '');
  const [slugEdited, setSlugEdited] = useState(false);
  const [showValidation, setShowValidation] = useState(false);
  const [notice, setNotice] = useState<
    | {
        tone: 'good' | 'warn' | 'bad';
        title: string;
        description?: string;
      }
    | null
  >(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isValidating, setIsValidating] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const validation = validateAgentForm(form, providers);
  const isDirty = serializeForm(form) !== baseline;

  useEffect(() => {
    if (selectedId === 'new') {
      if (!form.id && !isDirty && form.defaultProviderId !== (providers[0]?.id ?? '')) {
        const nextForm = { ...form, defaultProviderId: providers[0]?.id ?? '' };
        setForm(nextForm);
        setBaseline(serializeForm(nextForm));
      }
      return;
    }

    const selectedAgent = agents.find((agent) => agent.id === selectedId);
    if (selectedAgent) {
      if (!isDirty) {
        const nextForm = agentToForm(selectedAgent, providers[0]?.id ?? '');
        setForm(nextForm);
        setBaseline(serializeForm(nextForm));
      }
      return;
    }

    if (agents[0]) {
      const nextForm = agentToForm(agents[0], providers[0]?.id ?? '');
      setSelectedId(agents[0].id);
      setForm(nextForm);
      setBaseline(serializeForm(nextForm));
    } else {
      const nextForm = createDraft(providers[0]?.id ?? '');
      setSelectedId('new');
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
    const nextForm = agentToForm(agent, providers[0]?.id ?? '');
    setSelectedId(agent.id);
    setForm(nextForm);
    setBaseline(serializeForm(nextForm));
    setSlugEdited(true);
    setShowValidation(false);
    setNotice(null);
    setConfirmDelete(false);
  }

  function startNewAgent() {
    const nextForm = createDraft(providers[0]?.id ?? '');
    setSelectedId('new');
    setForm(nextForm);
    setBaseline(serializeForm(nextForm));
    setSlugEdited(false);
    setShowValidation(false);
    setNotice(null);
    setConfirmDelete(false);
  }

  function updateField<K extends keyof AgentFormState>(key: K, value: AgentFormState[K]) {
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
    updateField('slug', value);
  }

  function updateFieldRow(
    fieldId: string,
    patch: Partial<Omit<AgentFieldState, 'id'>>,
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
          id: createLocalId(),
          name: '',
          label: '',
          description: '',
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
        template.reasoningMode === 'chain_of_thought' ? 'chain_of_thought' : 'predict',
      inputFields: template.inputFields.map((field) => ({
        ...field,
        id: createLocalId(),
        description: field.description ?? '',
      })),
      outputMode: template.outputMode === 'json' ? 'json' : 'text',
      outputFieldName: template.outputFieldName,
      outputSchemaText: template.outputSchema
        ? JSON.stringify(template.outputSchema, null, 2)
        : '',
      defaultProviderId: form.defaultProviderId || providers[0]?.id || '',
      modelOverride: '',
      temperature: String(template.temperature),
      maxTokens: String(template.maxTokens),
      enabled: true,
      revision: 0,
      createdAt: '',
      updatedAt: '',
    };

    setSelectedId('new');
    setForm(nextForm);
    setBaseline(serializeForm(nextForm));
    setSlugEdited(false);
    setShowValidation(false);
    setNotice({
      tone: 'good',
      title: 'Template applied',
      description: `${template.name} has been loaded into the editor as a new draft.`,
    });
    setConfirmDelete(false);
  }

  function updateOutputMode(outputMode: 'text' | 'json') {
    setForm((current) => ({
      ...current,
      outputMode,
      outputSchemaText:
        outputMode === 'json'
          ? current.outputSchemaText.trim() || '{\n  "response": "string"\n}'
          : '',
    }));
  }

  function buildPayload(): AgentMutationPayload | null {
    if (validation.formError || Object.keys(validation.fieldErrors).length > 0) {
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
        label: field.label.trim() || humanize(field.name.trim()) || field.name.trim(),
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
        tone: 'bad',
        title: 'Agent settings need attention',
        description:
          validation.formError ?? 'Fix the highlighted fields before validating.',
      });
      return;
    }

    if (!apiAvailable) {
      setNotice({
        tone: 'warn',
        title: 'Server validation unavailable',
        description: 'Local validation passed, but this Control Plane build does not expose the /api/v1 agent validation routes yet.',
      });
      return;
    }

    setIsValidating(true);
    try {
      const result = await validateAgent(payload, form.id ?? undefined);
      setNotice({
        tone: result.valid ? 'good' : 'warn',
        title: result.valid ? 'Validation passed' : 'Validation returned warnings',
        description: result.normalized
          ? `${result.normalized.name} is ready to save.`
          : 'The Control Plane accepted the payload shape.',
      });
    } catch (error) {
      setNotice({
        tone: 'bad',
        title: 'Could not validate agent',
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
        tone: 'bad',
        title: 'Agent settings need attention',
        description:
          validation.formError ?? 'Fix the highlighted fields before saving.',
      });
      return;
    }

    setIsSaving(true);
    try {
      const saved = await saveAgent(payload, form.id ?? undefined);
      const nextForm = agentToForm(saved, providers[0]?.id ?? '');
      setSelectedId(saved.id);
      setForm(nextForm);
      setBaseline(serializeForm(nextForm));
      setSlugEdited(true);
      setShowValidation(false);
      setNotice({
        tone: 'good',
        title: form.id ? 'Agent updated' : 'Agent created',
        description: `${saved.name} is ready to run in the playground.`,
      });
      onAgentSaved(saved);
    } catch (error) {
      setNotice({
        tone: 'bad',
        title: 'Could not save agent',
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
        tone: 'good',
        title: 'Agent deleted',
        description: 'Any existing invocation history remains available in the playground recent-runs list.',
      });
    } catch (error) {
      setNotice({
        tone: 'bad',
        title: 'Could not delete agent',
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
            <button className="button button--secondary" type="button" onClick={startNewAgent}>
              New agent
            </button>
          </div>
        }
      />

      {warning ? (
        <InlineNotice tone={apiAvailable ? 'warn' : 'bad'} title={apiAvailable ? 'Bootstrap fallback in use' : 'Agent APIs unavailable'}>
          <p>{warning}</p>
        </InlineNotice>
      ) : null}

      {!canEdit ? (
        <InlineNotice tone="warn" title="A provider is required first">
          <p>Create at least one provider before saving agents. The backend validates <code>defaultProviderId</code> against the current provider list.</p>
        </InlineNotice>
      ) : null}

      <div className="page-grid page-grid--sidebar">
        <Panel
          title={`Saved agents (${agents.length})`}
          subtitle="Each agent captures instructions, inputs, output rules, and default provider routing."
        >
          {agents.length > 0 ? (
            <div className="stack-list">
              {agents.map((agent) => {
                const provider = providerMap.get(agent.defaultProviderId);
                return (
                  <button
                    key={agent.id}
                    type="button"
                    className={cx('resource-row', selectedId === agent.id && 'is-active')}
                    onClick={() => selectAgent(agent)}
                  >
                    <div className="resource-row__header">
                      <strong>{agent.name}</strong>
                      <StatusBadge status={agent.enabled ? 'enabled' : 'disabled'} label={agent.enabled ? 'Enabled' : 'Disabled'} />
                    </div>
                    <p>
                      {agent.outputMode.toUpperCase()} · {provider?.name ?? 'Missing provider'}
                    </p>
                    <div className="resource-row__meta-row">
                      <StatusBadge status={agent.reasoningMode} label={agent.reasoningMode === 'chain_of_thought' ? 'Chain of thought' : 'Predict'} tone="accent" />
                      <span className="muted-text">{agent.inputFields.length} input field{agent.inputFields.length === 1 ? '' : 's'}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          ) : (
            <EmptyState
              title="No agents saved"
              description="Start from a template or build one from scratch once a provider exists."
              action={
                <button className="button button--primary" type="button" onClick={startNewAgent}>
                  Create agent
                </button>
              }
            />
          )}
        </Panel>

        <Panel
          title={form.id ? 'Edit agent' : 'New agent'}
          subtitle="Agents are validated against provider IDs, input-field identifiers, output modes, and JSON schema requirements."
        >
          {notice ? (
            <InlineNotice tone={notice.tone} title={notice.title}>
              {notice.description ? <p>{notice.description}</p> : null}
            </InlineNotice>
          ) : null}

          {!apiAvailable ? (
            <InlineNotice tone="warn" title="Read-only in this Control Plane build">
              <p>System status endpoints are present, but the agent CRUD routes under <code>/api/v1</code> are not available yet.</p>
            </InlineNotice>
          ) : null}

          <fieldset className="form-fieldset" disabled={!apiAvailable || !canEdit || isSaving || isValidating}>
            <div className="form-section form-section--inline">
              <label className="field field--grow">
                <span className="field__label">Template</span>
                <select
                  className="select"
                  value={templateId}
                  onChange={(event) => setTemplateId(event.target.value)}
                >
                  <option value="">Select a template</option>
                  {agentTemplates.map((template) => (
                    <option key={template.id} value={template.id}>
                      {template.name}
                    </option>
                  ))}
                </select>
              </label>
              <button
                className="button button--secondary"
                type="button"
                onClick={applyTemplate}
                disabled={!templateId}
              >
                Apply template
              </button>
            </div>

            <div className="form-grid form-grid--two">
              <label className="field">
                <span className="field__label">Name</span>
                <input
                  className="input"
                  type="text"
                  value={form.name}
                  onChange={(event) => updateName(event.target.value)}
                  placeholder="e.g. Release-note summarizer"
                  aria-invalid={Boolean(showValidation && validation.fieldErrors.name)}
                />
                {showValidation && validation.fieldErrors.name ? <span className="field__error">{validation.fieldErrors.name}</span> : null}
              </label>

              <label className="field">
                <span className="field__label">Slug</span>
                <input
                  className="input mono"
                  type="text"
                  value={form.slug}
                  onChange={(event) => updateSlug(event.target.value)}
                  placeholder="release-note-summarizer"
                  aria-invalid={Boolean(showValidation && validation.fieldErrors.slug)}
                />
                {showValidation && validation.fieldErrors.slug ? <span className="field__error">{validation.fieldErrors.slug}</span> : null}
              </label>
            </div>

            <div className="form-grid form-grid--two">
              <label className="field">
                <span className="field__label">Description</span>
                <input
                  className="input"
                  type="text"
                  value={form.description}
                  onChange={(event) => updateField('description', event.target.value)}
                  placeholder="Short summary shown in the list and playground"
                />
              </label>

              <label className="field field--checkbox">
                <span className="field__label">Enabled</span>
                <label className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={form.enabled}
                    onChange={(event) => updateField('enabled', event.target.checked)}
                  />
                  <span>Allow the playground to run this agent.</span>
                </label>
              </label>
            </div>

            <label className="field">
              <span className="field__label">Instructions</span>
              <textarea
                className="textarea textarea--lg"
                value={form.instructions}
                onChange={(event) => updateField('instructions', event.target.value)}
                placeholder="Describe how the agent should behave, what to prioritize, and how to format its response."
                aria-invalid={Boolean(showValidation && validation.fieldErrors.instructions)}
              />
              {showValidation && validation.fieldErrors.instructions ? <span className="field__error">{validation.fieldErrors.instructions}</span> : null}
            </label>

            <div className="form-grid form-grid--two">
              <label className="field">
                <span className="field__label">Reasoning mode</span>
                <span className="segmented" role="radiogroup" aria-label="Reasoning mode">
                  {['predict', 'chain_of_thought'].map((mode) => (
                    <button
                      key={mode}
                      type="button"
                      className={cx('segmented__button', form.reasoningMode === mode && 'is-active')}
                      onClick={() => updateField('reasoningMode', mode as 'predict' | 'chain_of_thought')}
                    >
                      {mode === 'chain_of_thought' ? 'chain_of_thought' : 'predict'}
                    </button>
                  ))}
                </span>
              </label>

              <label className="field">
                <span className="field__label">Default provider</span>
                <select
                  className="select"
                  value={form.defaultProviderId}
                  onChange={(event) => updateField('defaultProviderId', event.target.value)}
                  aria-invalid={Boolean(showValidation && validation.fieldErrors.defaultProviderId)}
                >
                  <option value="">Select a provider</option>
                  {providers.map((provider) => (
                    <option key={provider.id} value={provider.id}>
                      {provider.name}
                    </option>
                  ))}
                </select>
                {showValidation && validation.fieldErrors.defaultProviderId ? <span className="field__error">{validation.fieldErrors.defaultProviderId}</span> : null}
              </label>
            </div>

            <div className="form-section">
              <div className="section-header-row">
                <div>
                  <h3>Input fields</h3>
                  <p>These fields render the playground form automatically.</p>
                </div>
                <button className="button button--secondary" type="button" onClick={addInputField}>
                  Add field
                </button>
              </div>
              <div className="input-field-list">
                {form.inputFields.map((field) => (
                  <div className="input-field-editor" key={field.id}>
                    <div className="form-grid form-grid--three">
                      <label className="field">
                        <span className="field__label">Name</span>
                        <input
                          className="input mono"
                          type="text"
                          value={field.name}
                          onChange={(event) => updateFieldRow(field.id, { name: event.target.value })}
                          placeholder="source_text"
                          aria-invalid={Boolean(showValidation && validation.fieldErrors[`field-name-${field.id}`])}
                        />
                        {showValidation && validation.fieldErrors[`field-name-${field.id}`] ? <span className="field__error">{validation.fieldErrors[`field-name-${field.id}`]}</span> : null}
                      </label>
                      <label className="field">
                        <span className="field__label">Label</span>
                        <input
                          className="input"
                          type="text"
                          value={field.label}
                          onChange={(event) => updateFieldRow(field.id, { label: event.target.value })}
                          placeholder="Source text"
                          aria-invalid={Boolean(showValidation && validation.fieldErrors[`field-label-${field.id}`])}
                        />
                        {showValidation && validation.fieldErrors[`field-label-${field.id}`] ? <span className="field__error">{validation.fieldErrors[`field-label-${field.id}`]}</span> : null}
                      </label>
                      <label className="field field--checkbox">
                        <span className="field__label">Required</span>
                        <label className="checkbox-row">
                          <input
                            type="checkbox"
                            checked={field.required}
                            onChange={(event) => updateFieldRow(field.id, { required: event.target.checked })}
                          />
                          <span>Must be present</span>
                        </label>
                      </label>
                    </div>
                    <label className="field">
                      <span className="field__label">Description</span>
                      <input
                        className="input"
                        type="text"
                        value={field.description}
                        onChange={(event) => updateFieldRow(field.id, { description: event.target.value })}
                        placeholder="Shown under the field in the playground"
                      />
                    </label>
                    <div className="button-row button-row--end">
                      <button
                        className="button button--quiet"
                        type="button"
                        onClick={() => removeInputField(field.id)}
                      >
                        Remove field
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="form-section">
              <div className="section-header-row">
                <div>
                  <h3>Output</h3>
                  <p>Text outputs render directly. JSON outputs must return a top-level object.</p>
                </div>
              </div>
              <div className="form-grid form-grid--two">
                <label className="field">
                  <span className="field__label">Output mode</span>
                  <span className="segmented" role="radiogroup" aria-label="Output mode">
                    {['text', 'json'].map((mode) => (
                      <button
                        key={mode}
                        type="button"
                        className={cx('segmented__button', form.outputMode === mode && 'is-active')}
                        onClick={() => updateOutputMode(mode as 'text' | 'json')}
                      >
                        {mode}
                      </button>
                    ))}
                  </span>
                </label>

                <label className="field">
                  <span className="field__label">Output field name</span>
                  <input
                    className="input mono"
                    type="text"
                    value={form.outputFieldName}
                    onChange={(event) => updateField('outputFieldName', event.target.value)}
                    placeholder="response"
                    aria-invalid={Boolean(showValidation && validation.fieldErrors.outputFieldName)}
                  />
                  {showValidation && validation.fieldErrors.outputFieldName ? <span className="field__error">{validation.fieldErrors.outputFieldName}</span> : null}
                </label>
              </div>

              {form.outputMode === 'json' ? (
                <label className="field">
                  <span className="field__label">Output schema (JSON object)</span>
                  <textarea
                    className="textarea textarea--lg mono"
                    value={form.outputSchemaText}
                    onChange={(event) => updateField('outputSchemaText', event.target.value)}
                    placeholder='{"theme": "string", "next_actions": ["string"]}'
                    aria-invalid={Boolean(showValidation && validation.fieldErrors.outputSchemaText)}
                  />
                  {showValidation && validation.fieldErrors.outputSchemaText ? <span className="field__error">{validation.fieldErrors.outputSchemaText}</span> : null}
                </label>
              ) : null}
            </div>

            <div className="form-section">
              <div className="section-header-row">
                <div>
                  <h3>Runtime defaults</h3>
                  <p>These values can still be overridden per run in the playground.</p>
                </div>
              </div>
              <div className="form-grid form-grid--two">
                <label className="field">
                  <span className="field__label">Model override</span>
                  <input
                    className="input mono"
                    type="text"
                    value={form.modelOverride}
                    onChange={(event) => updateField('modelOverride', event.target.value)}
                    placeholder="Optional: use a model other than the provider default"
                  />
                </label>

                <label className="field">
                  <span className="field__label">Temperature</span>
                  <input
                    className="input mono"
                    type="number"
                    min="0"
                    step="0.1"
                    value={form.temperature}
                    onChange={(event) => updateField('temperature', event.target.value)}
                    aria-invalid={Boolean(showValidation && validation.fieldErrors.temperature)}
                  />
                  {showValidation && validation.fieldErrors.temperature ? <span className="field__error">{validation.fieldErrors.temperature}</span> : null}
                </label>
              </div>
              <div className="form-grid form-grid--two">
                <label className="field">
                  <span className="field__label">Max tokens</span>
                  <input
                    className="input mono"
                    type="number"
                    min="32"
                    step="1"
                    value={form.maxTokens}
                    onChange={(event) => updateField('maxTokens', event.target.value)}
                    aria-invalid={Boolean(showValidation && validation.fieldErrors.maxTokens)}
                  />
                  {showValidation && validation.fieldErrors.maxTokens ? <span className="field__error">{validation.fieldErrors.maxTokens}</span> : null}
                </label>
              </div>
            </div>
          </fieldset>

          {form.outputMode === 'json' && validation.parsedOutputSchema ? (
            <details className="details-block" open>
              <summary>Parsed output schema preview</summary>
              <JsonBlock value={validation.parsedOutputSchema} />
            </details>
          ) : null}

          <div className="editor-footer">
            <div className="editor-footer__meta">
              <span>Updated {form.updatedAt ? formatDateTime(form.updatedAt) : '—'}</span>
              {form.revision > 0 ? <span>Revision {form.revision}</span> : null}
              {form.createdAt ? <span>Created {formatRelativeTime(form.createdAt)}</span> : null}
            </div>
            <div className="button-row">
              <button
                className="button button--secondary"
                type="button"
                onClick={() => {
                  void handleValidateAgent();
                }}
                disabled={!canSubmit}
              >
                {isValidating ? 'Validating…' : 'Validate'}
              </button>
              <button
                className="button button--danger"
                type="button"
                onClick={() => {
                  void handleDeleteAgent();
                }}
                disabled={!apiAvailable || isSaving || isValidating}
              >
                {form.id ? (confirmDelete ? 'Confirm delete' : 'Delete agent') : 'Discard draft'}
              </button>
              <button
                className="button button--primary"
                type="button"
                onClick={() => {
                  void handleSaveAgent();
                }}
                disabled={!canSubmit}
              >
                {isSaving ? 'Saving…' : 'Save agent'}
              </button>
            </div>
          </div>
        </Panel>
      </div>
    </div>
  );
}

function validateAgentForm(
  form: AgentFormState,
  providers: ProviderConfig[],
): AgentValidationState {
  const fieldErrors: AgentValidationState['fieldErrors'] = {};

  if (form.name.trim().length < 2) {
    fieldErrors.name = 'Agent names must be at least 2 characters.';
  }
  if (!/^[a-z0-9][a-z0-9-]*$/.test(form.slug.trim())) {
    fieldErrors.slug = 'Slugs may only use lowercase letters, numbers, and hyphens.';
  }
  if (form.instructions.trim().length < 10) {
    fieldErrors.instructions = 'Instructions must be at least 10 characters.';
  }
  if (!/^[a-zA-Z][a-zA-Z0-9_]*$/.test(form.outputFieldName.trim())) {
    fieldErrors.outputFieldName = 'Use a safe identifier such as response or summary_json.';
  }

  const seenNames = new Set<string>();
  form.inputFields.forEach((field) => {
    const trimmedName = field.name.trim();
    if (!/^[a-zA-Z][a-zA-Z0-9_]*$/.test(trimmedName)) {
      fieldErrors[`field-name-${field.id}`] = 'Use a safe identifier such as source_text.';
    } else if (seenNames.has(trimmedName)) {
      fieldErrors[`field-name-${field.id}`] = 'Field names must be unique within the agent.';
    }
    seenNames.add(trimmedName);

    if (!field.label.trim() && !trimmedName) {
      fieldErrors[`field-label-${field.id}`] = 'Add a label or name so the playground can render this field.';
    }
  });

  if (form.inputFields.length === 0) {
    fieldErrors['field-name-empty'] = 'Add at least one input field.';
  }

  if (!providers.some((provider) => provider.id === form.defaultProviderId)) {
    fieldErrors.defaultProviderId = 'Select an existing default provider.';
  }

  if (form.temperature.trim() === '' || Number.isNaN(Number(form.temperature))) {
    fieldErrors.temperature = 'Enter a numeric temperature, such as 0.2.';
  }

  if (
    form.maxTokens.trim() === '' ||
    !Number.isInteger(Number(form.maxTokens)) ||
    Number(form.maxTokens) < 32
  ) {
    fieldErrors.maxTokens = 'Max tokens must be an integer of at least 32.';
  }

  let parsedOutputSchema: Record<string, unknown> | null = null;
  if (form.outputMode === 'json') {
    if (!form.outputSchemaText.trim()) {
      fieldErrors.outputSchemaText = 'JSON output agents need a non-empty output schema object.';
    } else {
      try {
        const parsed = JSON.parse(form.outputSchemaText);
        if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
          fieldErrors.outputSchemaText = 'The output schema must be a JSON object at the top level.';
        } else {
          parsedOutputSchema = parsed as Record<string, unknown>;
        }
      } catch {
        fieldErrors.outputSchemaText = 'The output schema must be valid JSON.';
      }
    }
  }

  const formError = Object.keys(fieldErrors).length
    ? 'The agent form has invalid or missing values.'
    : null;

  return { fieldErrors, formError, parsedOutputSchema };
}

function agentToForm(agent: AgentConfig, fallbackProviderId: string): AgentFormState {
  return {
    id: agent.id,
    name: agent.name,
    slug: agent.slug,
    description: agent.description ?? '',
    instructions: agent.instructions,
    reasoningMode:
      agent.reasoningMode === 'chain_of_thought' ? 'chain_of_thought' : 'predict',
    inputFields: agent.inputFields.map((field) => ({
      ...field,
      id: createLocalId(),
      description: field.description ?? '',
    })),
    outputMode: agent.outputMode === 'json' ? 'json' : 'text',
    outputFieldName: agent.outputFieldName,
    outputSchemaText: agent.outputSchema
      ? JSON.stringify(agent.outputSchema, null, 2)
      : '',
    defaultProviderId: agent.defaultProviderId || fallbackProviderId,
    modelOverride: agent.modelOverride ?? '',
    temperature: String(agent.temperature),
    maxTokens: String(agent.maxTokens),
    enabled: agent.enabled,
    revision: agent.revision,
    createdAt: agent.createdAt ?? '',
    updatedAt: agent.updatedAt ?? '',
  };
}

function createDraft(defaultProviderId: string): AgentFormState {
  return {
    id: null,
    name: '',
    slug: '',
    description: '',
    instructions: '',
    reasoningMode: 'predict',
    inputFields: [
      {
        id: createLocalId(),
        name: 'input_text',
        label: 'Input text',
        description: '',
        required: true,
      },
    ],
    outputMode: 'text',
    outputFieldName: 'response',
    outputSchemaText: '',
    defaultProviderId,
    modelOverride: '',
    temperature: '0.2',
    maxTokens: '700',
    enabled: true,
    revision: 0,
    createdAt: '',
    updatedAt: '',
  };
}

function serializeForm(form: AgentFormState): string {
  return JSON.stringify({
    id: form.id,
    name: form.name,
    slug: form.slug,
    description: form.description,
    instructions: form.instructions,
    reasoningMode: form.reasoningMode,
    inputFields: form.inputFields.map(({ id, ...field }) => field),
    outputMode: form.outputMode,
    outputFieldName: form.outputFieldName,
    outputSchemaText: form.outputSchemaText,
    defaultProviderId: form.defaultProviderId,
    modelOverride: form.modelOverride,
    temperature: form.temperature,
    maxTokens: form.maxTokens,
    enabled: form.enabled,
  });
}

function slugify(value: string): string {
  const slug = value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return slug || 'agent';
}

function createLocalId(): string {
  return `field-${Math.random().toString(36).slice(2, 10)}`;
}

function humanize(value: string): string | null {
  if (!value) {
    return null;
  }
  return value
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/(^|\s)(\w)/g, (_, prefix: string, char: string) => `${prefix}${char.toUpperCase()}`);
}

function emptyToNull(value: string): string | null {
  return value.trim() ? value.trim() : null;
}
