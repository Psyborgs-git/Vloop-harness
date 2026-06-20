import { useEffect, useMemo, useState } from 'react';
import {
  DEFAULT_PROVIDER_CATALOG,
  deleteProvider,
  getErrorMessage,
  saveProvider,
  testProvider,
  type ProviderConfig,
  type ProviderMutationPayload,
  type ProviderTypeSpec,
  type SecretMode,
} from '../lib/api';
import {
  EmptyState,
  InlineNotice,
  PageHeader,
  Panel,
  StatusBadge,
  cx,
  formatDateTime,
  formatRelativeTime,
} from '../components/ui';

interface ProvidersViewProps {
  providers: ProviderConfig[];
  providerCatalog: ProviderTypeSpec[];
  apiAvailable: boolean;
  warning: string | null;
  onProviderSaved: (provider: ProviderConfig) => void;
  onProviderDeleted: (providerId: string) => void;
}

interface ProviderFormState {
  id: string | null;
  name: string;
  providerType: string;
  enabled: boolean;
  defaultModel: string;
  apiBase: string;
  apiVersion: string;
  organization: string;
  secretMode: SecretMode;
  secretEnvVar: string;
  sessionSecret: string;
  hasSecret: boolean;
  revision: number;
  lastTestStatus: string;
  lastTestError: string;
  lastTestedAt: string;
  createdAt: string;
  updatedAt: string;
}

interface ProviderValidation {
  fieldErrors: Partial<Record<'name' | 'defaultModel' | 'secretEnvVar' | 'sessionSecret' | 'apiBase' | 'secretMode', string>>;
  formError: string | null;
}

export function ProvidersView({
  providers,
  providerCatalog,
  apiAvailable,
  warning,
  onProviderSaved,
  onProviderDeleted,
}: ProvidersViewProps) {
  const catalog = providerCatalog.length > 0 ? providerCatalog : DEFAULT_PROVIDER_CATALOG;
  const catalogMap = useMemo(
    () => new Map(catalog.map((entry) => [entry.key, entry])),
    [catalog],
  );
  const fallbackSpec = catalog[0];

  const [selectedId, setSelectedId] = useState<string | 'new'>(providers[0]?.id ?? 'new');
  const [form, setForm] = useState<ProviderFormState>(() =>
    providers[0] ? providerToForm(providers[0]) : createDraft(fallbackSpec),
  );
  const [baseline, setBaseline] = useState<string>(() => serializeForm(form));
  const [notice, setNotice] = useState<
    | {
        tone: 'good' | 'warn' | 'bad';
        title: string;
        description?: string;
      }
    | null
  >(null);
  const [showValidation, setShowValidation] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const currentSpec = catalogMap.get(form.providerType) ?? fallbackSpec;
  const validation = validateProviderForm(form, currentSpec);
  const isDirty = serializeForm(form) !== baseline;

  useEffect(() => {
    if (selectedId === 'new') {
      if (!form.id && !isDirty) {
        const nextDraft = createDraft(currentSpec);
        setForm(nextDraft);
        setBaseline(serializeForm(nextDraft));
      }
      return;
    }

    const selectedProvider = providers.find((provider) => provider.id === selectedId);
    if (selectedProvider) {
      if (!isDirty) {
        const nextForm = providerToForm(selectedProvider);
        setForm(nextForm);
        setBaseline(serializeForm(nextForm));
      }
      return;
    }

    if (providers[0]) {
      const nextForm = providerToForm(providers[0]);
      setSelectedId(providers[0].id);
      setForm(nextForm);
      setBaseline(serializeForm(nextForm));
    } else {
      const nextForm = createDraft(fallbackSpec);
      setSelectedId('new');
      setForm(nextForm);
      setBaseline(serializeForm(nextForm));
    }
  }, [currentSpec, fallbackSpec, form.id, isDirty, providers, selectedId]);

  function selectProvider(provider: ProviderConfig) {
    const nextForm = providerToForm(provider);
    setSelectedId(provider.id);
    setForm(nextForm);
    setBaseline(serializeForm(nextForm));
    setShowValidation(false);
    setNotice(null);
    setConfirmDelete(false);
  }

  function startNewProvider() {
    const nextForm = createDraft(fallbackSpec);
    setSelectedId('new');
    setForm(nextForm);
    setBaseline(serializeForm(nextForm));
    setShowValidation(false);
    setNotice(null);
    setConfirmDelete(false);
  }

  function updateField<K extends keyof ProviderFormState>(key: K, value: ProviderFormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
    setConfirmDelete(false);
  }

  function handleProviderTypeChange(providerType: string) {
    const previousSpec = catalogMap.get(form.providerType) ?? fallbackSpec;
    const nextSpec = catalogMap.get(providerType) ?? fallbackSpec;
    const nextSecretMode = nextSpec.secretModes.includes(form.secretMode)
      ? form.secretMode
      : nextSpec.secretModes[0] ?? 'none';

    setForm((current) => ({
      ...current,
      providerType,
      defaultModel:
        !current.defaultModel || current.defaultModel === previousSpec.defaultModel
          ? nextSpec.defaultModel
          : current.defaultModel,
      apiBase:
        !current.apiBase || current.apiBase === (previousSpec.apiBaseHint ?? '')
          ? nextSpec.apiBaseHint ?? ''
          : current.apiBase,
      apiVersion:
        !current.apiVersion || current.apiVersion === (previousSpec.apiVersionHint ?? '')
          ? nextSpec.apiVersionHint ?? ''
          : current.apiVersion,
      secretMode: nextSecretMode,
      secretEnvVar: nextSecretMode === 'env' ? current.secretEnvVar : '',
      sessionSecret: nextSecretMode === 'session' ? current.sessionSecret : '',
      hasSecret: nextSecretMode === 'none' ? true : current.hasSecret,
    }));
    setConfirmDelete(false);
  }

  async function persistProvider(): Promise<ProviderConfig | null> {
    setShowValidation(true);
    if (validation.formError || Object.keys(validation.fieldErrors).length > 0) {
      setNotice({
        tone: 'bad',
        title: 'Provider settings need attention',
        description:
          validation.formError ?? 'Fix the highlighted fields before saving.',
      });
      return null;
    }

    const payload: ProviderMutationPayload = {
      name: form.name.trim(),
      providerType: form.providerType,
      enabled: form.enabled,
      defaultModel: form.defaultModel.trim(),
      apiBase: emptyToNull(form.apiBase),
      apiVersion: emptyToNull(form.apiVersion),
      organization: emptyToNull(form.organization),
      secretMode: form.secretMode,
      secretEnvVar: emptyToNull(form.secretEnvVar),
      sessionSecret: form.sessionSecret,
      clearSessionSecret: false,
    };

    setIsSaving(true);
    try {
      const saved = await saveProvider(payload, form.id ?? undefined);
      const nextForm = providerToForm(saved);
      setSelectedId(saved.id);
      setForm(nextForm);
      setBaseline(serializeForm(nextForm));
      setShowValidation(false);
      setNotice({
        tone: 'good',
        title: form.id ? 'Provider updated' : 'Provider created',
        description: `${saved.name} is ready for testing or agent routing.`,
      });
      onProviderSaved(saved);
      return saved;
    } catch (error) {
      setNotice({
        tone: 'bad',
        title: 'Could not save provider',
        description: getErrorMessage(error),
      });
      return null;
    } finally {
      setIsSaving(false);
    }
  }

  async function handleTestProvider() {
    setNotice(null);
    const provider = form.id && !isDirty ? providers.find((entry) => entry.id === form.id) ?? null : await persistProvider();
    if (!provider?.id) {
      return;
    }

    setIsTesting(true);
    try {
      const result = await testProvider(provider.id);
      const nextForm = providerToForm(result.provider);
      setSelectedId(result.provider.id);
      setForm(nextForm);
      setBaseline(serializeForm(nextForm));
      setNotice({
        tone: result.status === 'ok' ? 'good' : 'bad',
        title: result.status === 'ok' ? 'Provider test passed' : 'Provider test failed',
        description: result.preview ?? result.error ?? 'The Control Plane did not return extra test output.',
      });
      onProviderSaved(result.provider);
    } catch (error) {
      setNotice({
        tone: 'bad',
        title: 'Could not test provider',
        description: getErrorMessage(error),
      });
    } finally {
      setIsTesting(false);
    }
  }

  async function handleDeleteProvider() {
    if (!form.id) {
      startNewProvider();
      return;
    }

    if (!confirmDelete) {
      setConfirmDelete(true);
      return;
    }

    try {
      await deleteProvider(form.id);
      onProviderDeleted(form.id);
      const remaining = providers.filter((provider) => provider.id !== form.id);
      if (remaining[0]) {
        selectProvider(remaining[0]);
      } else {
        startNewProvider();
      }
      setNotice({
        tone: 'good',
        title: 'Provider deleted',
        description: 'Agent references are not auto-rewritten, so review any agents that used this provider.',
      });
    } catch (error) {
      setNotice({
        tone: 'bad',
        title: 'Could not delete provider',
        description: getErrorMessage(error),
      });
    } finally {
      setConfirmDelete(false);
    }
  }

  const canSubmit = apiAvailable && !isSaving && !isTesting;
  const isSessionMode = form.secretMode === 'session';
  const isEnvMode = form.secretMode === 'env';
  const hasRuntimeSecret =
    form.secretMode === 'none' || form.hasSecret || form.sessionSecret.trim().length > 0;

  return (
    <div className="page-stack">
      <PageHeader
        title="Providers"
        description="Configure model backends, secrets, and connection details that agents can route through."
        actions={
          <div className="button-row">
            <button className="button button--secondary" type="button" onClick={startNewProvider}>
              New provider
            </button>
          </div>
        }
      />

      {warning ? (
        <InlineNotice tone={apiAvailable ? 'warn' : 'bad'} title={apiAvailable ? 'Bootstrap fallback in use' : 'Provider APIs unavailable'}>
          <p>{warning}</p>
        </InlineNotice>
      ) : null}

      <div className="page-grid page-grid--sidebar">
        <Panel
          title={`Configured providers (${providers.length})`}
          subtitle="Each provider stores a model default, a secret strategy, and its latest connectivity test."
        >
          {providers.length > 0 ? (
            <div className="stack-list">
              {providers.map((provider) => (
                <button
                  key={provider.id}
                  type="button"
                  className={cx('resource-row', selectedId === provider.id && 'is-active')}
                  onClick={() => selectProvider(provider)}
                >
                  <div className="resource-row__header">
                    <strong>{provider.name}</strong>
                    <StatusBadge status={provider.lastTestStatus} label={provider.lastTestStatus === 'unknown' ? 'Untested' : undefined} />
                  </div>
                  <p>
                    {provider.providerType} · {provider.defaultModel}
                  </p>
                  <div className="resource-row__meta-row">
                    <StatusBadge status={provider.enabled ? 'enabled' : 'disabled'} label={provider.enabled ? 'Enabled' : 'Disabled'} />
                    <StatusBadge
                      status={provider.hasSecret ? 'ready' : 'pending'}
                      label={provider.hasSecret ? 'Secret ready' : 'Secret missing'}
                      tone={provider.hasSecret ? 'good' : 'warn'}
                    />
                  </div>
                </button>
              ))}
            </div>
          ) : (
            <EmptyState
              title="No providers configured"
              description="Start with the mock provider for a safe local loop, or add a real backend like Ollama, OpenAI, Anthropic, OpenRouter, or Azure OpenAI."
              action={
                <button className="button button--primary" type="button" onClick={startNewProvider}>
                  Create provider
                </button>
              }
            />
          )}
        </Panel>

        <Panel
          title={form.id ? 'Edit provider' : 'New provider'}
          subtitle="Secrets remain write-only. Session secrets can be rotated by entering a new value before saving."
        >
          {notice ? (
            <InlineNotice tone={notice.tone} title={notice.title}>
              {notice.description ? <p>{notice.description}</p> : null}
            </InlineNotice>
          ) : null}

          {!apiAvailable ? (
            <InlineNotice tone="warn" title="Read-only in this Control Plane build">
              <p>System status endpoints are present, but the provider CRUD routes under <code>/api/v1</code> are not available yet.</p>
            </InlineNotice>
          ) : null}

          <fieldset className="form-fieldset" disabled={!apiAvailable || isSaving || isTesting}>
            <div className="form-section">
              <label className="field">
                <span className="field__label">Provider type</span>
                <span className="segmented segmented--wrap" role="radiogroup" aria-label="Provider type">
                  {catalog.map((entry) => (
                    <button
                      key={entry.key}
                      type="button"
                      className={cx('segmented__button', form.providerType === entry.key && 'is-active')}
                      onClick={() => handleProviderTypeChange(entry.key)}
                    >
                      {entry.key}
                    </button>
                  ))}
                </span>
              </label>

              <div className="hint-card">
                <strong>{currentSpec.label}</strong>
                <p>{currentSpec.description}</p>
                <div className="hint-card__meta">
                  <span>Default model: <code>{currentSpec.defaultModel}</code></span>
                  <span>Allowed secrets: {currentSpec.secretModes.join(', ')}</span>
                </div>
                {currentSpec.modelExamples.length > 0 ? (
                  <p className="muted-text">Examples: {currentSpec.modelExamples.join(' · ')}</p>
                ) : null}
              </div>
            </div>

            <div className="form-grid form-grid--two">
              <label className="field">
                <span className="field__label">Name</span>
                <input
                  className="input"
                  type="text"
                  value={form.name}
                  onChange={(event) => updateField('name', event.target.value)}
                  placeholder="e.g. Local Ollama"
                  aria-invalid={Boolean(showValidation && validation.fieldErrors.name)}
                />
                {showValidation && validation.fieldErrors.name ? <span className="field__error">{validation.fieldErrors.name}</span> : null}
              </label>

              <label className="field field--checkbox">
                <span className="field__label">Enabled</span>
                <label className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={form.enabled}
                    onChange={(event) => updateField('enabled', event.target.checked)}
                  />
                  <span>Allow agents and the playground to use this provider.</span>
                </label>
              </label>
            </div>

            <div className="form-grid form-grid--two">
              <label className="field">
                <span className="field__label">Default model</span>
                <input
                  className="input mono"
                  type="text"
                  value={form.defaultModel}
                  onChange={(event) => updateField('defaultModel', event.target.value)}
                  placeholder={currentSpec.defaultModel}
                  aria-invalid={Boolean(showValidation && validation.fieldErrors.defaultModel)}
                />
                {showValidation && validation.fieldErrors.defaultModel ? <span className="field__error">{validation.fieldErrors.defaultModel}</span> : null}
              </label>

              <label className="field">
                <span className="field__label">API base</span>
                <input
                  className="input mono"
                  type="text"
                  value={form.apiBase}
                  onChange={(event) => updateField('apiBase', event.target.value)}
                  placeholder={currentSpec.apiBaseHint ?? 'Optional'}
                  aria-invalid={Boolean(showValidation && validation.fieldErrors.apiBase)}
                />
                {currentSpec.apiBaseHint ? <span className="field__hint">Suggested: {currentSpec.apiBaseHint}</span> : null}
                {showValidation && validation.fieldErrors.apiBase ? <span className="field__error">{validation.fieldErrors.apiBase}</span> : null}
              </label>
            </div>

            <div className="form-grid form-grid--two">
              <label className="field">
                <span className="field__label">API version</span>
                <input
                  className="input mono"
                  type="text"
                  value={form.apiVersion}
                  onChange={(event) => updateField('apiVersion', event.target.value)}
                  placeholder={currentSpec.apiVersionHint ?? 'Optional'}
                />
              </label>

              <label className="field">
                <span className="field__label">Organization</span>
                <input
                  className="input"
                  type="text"
                  value={form.organization}
                  onChange={(event) => updateField('organization', event.target.value)}
                  placeholder="Optional org or project identifier"
                />
              </label>
            </div>

            <div className="form-section">
              <label className="field">
                <span className="field__label">Secret mode</span>
                <span className="segmented" role="radiogroup" aria-label="Secret mode">
                  {currentSpec.secretModes.map((mode) => (
                    <button
                      key={mode}
                      type="button"
                      className={cx('segmented__button', form.secretMode === mode && 'is-active')}
                      onClick={() => updateField('secretMode', mode)}
                    >
                      {mode}
                    </button>
                  ))}
                </span>
                {showValidation && validation.fieldErrors.secretMode ? <span className="field__error">{validation.fieldErrors.secretMode}</span> : null}
              </label>

              {isEnvMode ? (
                <label className="field">
                  <span className="field__label">Environment variable name</span>
                  <input
                    className="input mono"
                    type="text"
                    value={form.secretEnvVar}
                    onChange={(event) => updateField('secretEnvVar', event.target.value)}
                    placeholder="OPENAI_API_KEY"
                    aria-invalid={Boolean(showValidation && validation.fieldErrors.secretEnvVar)}
                  />
                  <span className="field__hint">The Control Plane reads this value from its own process environment at runtime.</span>
                  {showValidation && validation.fieldErrors.secretEnvVar ? <span className="field__error">{validation.fieldErrors.secretEnvVar}</span> : null}
                </label>
              ) : null}

              {isSessionMode ? (
                <label className="field">
                  <span className="field__label">Session secret</span>
                  <input
                    className="input"
                    type="password"
                    value={form.sessionSecret}
                    onChange={(event) => updateField('sessionSecret', event.target.value)}
                    placeholder={form.hasSecret ? 'Enter a new secret to rotate it' : 'Enter a session secret'}
                    aria-invalid={Boolean(showValidation && validation.fieldErrors.sessionSecret)}
                  />
                  <span className="field__hint">Write-only. The current value is never read back into the UI.</span>
                  {showValidation && validation.fieldErrors.sessionSecret ? <span className="field__error">{validation.fieldErrors.sessionSecret}</span> : null}
                </label>
              ) : null}

              <div className="status-strip">
                <StatusBadge
                  status={hasRuntimeSecret ? 'ready' : 'pending'}
                  label={hasRuntimeSecret ? 'Secret available' : 'Secret missing'}
                  tone={hasRuntimeSecret ? 'good' : 'warn'}
                />
                <StatusBadge status={form.lastTestStatus} label={form.lastTestStatus === 'unknown' ? 'Not tested yet' : undefined} />
                {form.lastTestedAt ? <span className="muted-text">Tested {formatRelativeTime(form.lastTestedAt)}</span> : null}
              </div>
              {form.lastTestError ? <p className="field__error">Last test error: {form.lastTestError}</p> : null}
            </div>
          </fieldset>

          <div className="editor-footer">
            <div className="editor-footer__meta">
              <span>Updated {form.updatedAt ? formatDateTime(form.updatedAt) : '—'}</span>
              {form.revision > 0 ? <span>Revision {form.revision}</span> : null}
            </div>
            <div className="button-row">
              <button
                className="button button--secondary"
                type="button"
                onClick={handleTestProvider}
                disabled={!canSubmit}
              >
                {isTesting ? 'Testing…' : 'Test provider'}
              </button>
              <button
                className="button button--danger"
                type="button"
                onClick={handleDeleteProvider}
                disabled={!apiAvailable || isSaving || isTesting}
              >
                {form.id ? (confirmDelete ? 'Confirm delete' : 'Delete provider') : 'Discard draft'}
              </button>
              <button
                className="button button--primary"
                type="button"
                onClick={() => {
                  void persistProvider();
                }}
                disabled={!canSubmit}
              >
                {isSaving ? 'Saving…' : 'Save provider'}
              </button>
            </div>
          </div>
        </Panel>
      </div>
    </div>
  );
}

function providerToForm(provider: ProviderConfig): ProviderFormState {
  return {
    id: provider.id,
    name: provider.name,
    providerType: provider.providerType,
    enabled: provider.enabled,
    defaultModel: provider.defaultModel,
    apiBase: provider.apiBase ?? '',
    apiVersion: provider.apiVersion ?? '',
    organization: provider.organization ?? '',
    secretMode: provider.secretMode,
    secretEnvVar: provider.secretEnvVar ?? '',
    sessionSecret: '',
    hasSecret: provider.hasSecret,
    revision: provider.revision,
    lastTestStatus: provider.lastTestStatus,
    lastTestError: provider.lastTestError ?? '',
    lastTestedAt: provider.lastTestedAt ?? '',
    createdAt: provider.createdAt ?? '',
    updatedAt: provider.updatedAt ?? '',
  };
}

function createDraft(spec: ProviderTypeSpec): ProviderFormState {
  return {
    id: null,
    name: '',
    providerType: spec.key,
    enabled: true,
    defaultModel: spec.defaultModel,
    apiBase: spec.apiBaseHint ?? '',
    apiVersion: spec.apiVersionHint ?? '',
    organization: '',
    secretMode: spec.secretModes[0] ?? 'none',
    secretEnvVar: '',
    sessionSecret: '',
    hasSecret: spec.secretModes[0] === 'none',
    revision: 0,
    lastTestStatus: 'unknown',
    lastTestError: '',
    lastTestedAt: '',
    createdAt: '',
    updatedAt: '',
  };
}

function validateProviderForm(
  form: ProviderFormState,
  spec: ProviderTypeSpec,
): ProviderValidation {
  const fieldErrors: ProviderValidation['fieldErrors'] = {};

  if (form.name.trim().length < 2) {
    fieldErrors.name = 'Provider names must be at least 2 characters.';
  }
  if (!form.defaultModel.trim()) {
    fieldErrors.defaultModel = 'Enter the default model string the Control Plane should resolve.';
  }
  if (!spec.secretModes.includes(form.secretMode)) {
    fieldErrors.secretMode = `This provider type supports: ${spec.secretModes.join(', ')}.`;
  }
  if (form.secretMode === 'env' && !form.secretEnvVar.trim()) {
    fieldErrors.secretEnvVar = 'Enter the environment variable that holds this provider secret.';
  }
  if (form.secretMode === 'session' && !form.id && !form.sessionSecret.trim()) {
    fieldErrors.sessionSecret = 'New session-secret providers need a secret before they can be saved.';
  }
  if (
    form.apiBase.trim() &&
    form.apiBase.startsWith('http://') &&
    !spec.localOnlyHttp
  ) {
    fieldErrors.apiBase = 'Remote provider API bases must use https://.';
  }
  if (
    spec.localOnlyHttp &&
    form.apiBase.trim() &&
    !/^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/i.test(form.apiBase.trim())
  ) {
    fieldErrors.apiBase =
      'Ollama API bases must point at http://127.0.0.1 or http://localhost.';
  }

  const formError = Object.keys(fieldErrors).length
    ? 'The provider form has invalid or missing values.'
    : null;

  return { fieldErrors, formError };
}

function serializeForm(form: ProviderFormState): string {
  return JSON.stringify({
    id: form.id,
    name: form.name,
    providerType: form.providerType,
    enabled: form.enabled,
    defaultModel: form.defaultModel,
    apiBase: form.apiBase,
    apiVersion: form.apiVersion,
    organization: form.organization,
    secretMode: form.secretMode,
    secretEnvVar: form.secretEnvVar,
    sessionSecret: form.sessionSecret,
  });
}

function emptyToNull(value: string): string | null {
  return value.trim() ? value.trim() : null;
}
