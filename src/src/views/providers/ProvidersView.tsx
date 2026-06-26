import { useEffect, useMemo, useState } from "react";
import {
  DEFAULT_PROVIDER_CATALOG,
  deleteProvider,
  getErrorMessage,
  saveProvider,
  testProvider,
  type ProviderConfig,
  type ProviderMutationPayload,
  type ProviderTypeSpec,
} from "../../lib/api";
import { InlineNotice, PageHeader, Panel } from "../../components/ui";
import type { ProviderFormState } from "./ProviderFormTypes";
import {
  createDraft,
  emptyToNull,
  providerToForm,
  serializeForm,
  validateProviderForm,
} from "./ProviderFormHelpers";
import { ProviderList } from "./ProviderList";
import { ProviderForm } from "./ProviderForm";

interface ProvidersViewProps {
  providers: ProviderConfig[];
  providerCatalog: ProviderTypeSpec[];
  apiAvailable: boolean;
  warning: string | null;
  onProviderSaved: (provider: ProviderConfig) => void;
  onProviderDeleted: (providerId: string) => void;
}

export function ProvidersView({
  providers,
  providerCatalog,
  apiAvailable,
  warning,
  onProviderSaved,
  onProviderDeleted,
}: ProvidersViewProps) {
  const catalog =
    providerCatalog.length > 0 ? providerCatalog : DEFAULT_PROVIDER_CATALOG;
  const catalogMap = useMemo(
    () => new Map(catalog.map((entry) => [entry.key, entry])),
    [catalog],
  );
  const fallbackSpec = catalog[0];

  const [selectedId, setSelectedId] = useState<string | "new">(
    providers[0]?.id ?? "new",
  );
  const [form, setForm] = useState<ProviderFormState>(() =>
    providers[0] ? providerToForm(providers[0]) : createDraft(fallbackSpec),
  );
  const [baseline, setBaseline] = useState<string>(() => serializeForm(form));
  const [notice, setNotice] = useState<{
    tone: "good" | "warn" | "bad";
    title: string;
    description?: string;
  } | null>(null);
  const [showValidation, setShowValidation] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const currentSpec = catalogMap.get(form.providerType) ?? fallbackSpec;
  const validation = validateProviderForm(form, currentSpec);
  const isDirty = serializeForm(form) !== baseline;

  useEffect(() => {
    if (selectedId === "new") {
      if (!form.id && !isDirty) {
        const nextDraft = createDraft(currentSpec);
        setForm(nextDraft);
        setBaseline(serializeForm(nextDraft));
      }
      return;
    }

    const selectedProvider = providers.find(
      (provider) => provider.id === selectedId,
    );
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
      setSelectedId("new");
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
    setSelectedId("new");
    setForm(nextForm);
    setBaseline(serializeForm(nextForm));
    setShowValidation(false);
    setNotice(null);
    setConfirmDelete(false);
  }

  function updateField<K extends keyof ProviderFormState>(
    key: K,
    value: ProviderFormState[K],
  ) {
    setForm((current) => ({ ...current, [key]: value }));
    setConfirmDelete(false);
  }

  function handleProviderTypeChange(providerType: string) {
    const previousSpec = catalogMap.get(form.providerType) ?? fallbackSpec;
    const nextSpec = catalogMap.get(providerType) ?? fallbackSpec;
    const nextSecretMode = nextSpec.secretModes.includes(form.secretMode)
      ? form.secretMode
      : (nextSpec.secretModes[0] ?? "none");

    setForm((current) => ({
      ...current,
      providerType,
      defaultModel:
        !current.defaultModel ||
        current.defaultModel === previousSpec.defaultModel
          ? nextSpec.defaultModel
          : current.defaultModel,
      apiBase:
        !current.apiBase || current.apiBase === (previousSpec.apiBaseHint ?? "")
          ? (nextSpec.apiBaseHint ?? "")
          : current.apiBase,
      apiVersion:
        !current.apiVersion ||
        current.apiVersion === (previousSpec.apiVersionHint ?? "")
          ? (nextSpec.apiVersionHint ?? "")
          : current.apiVersion,
      secretMode: nextSecretMode,
      secretEnvVar: nextSecretMode === "env" ? current.secretEnvVar : "",
      sessionSecret: nextSecretMode === "session" ? current.sessionSecret : "",
      hasSecret: nextSecretMode === "none" ? true : current.hasSecret,
    }));
    setConfirmDelete(false);
  }

  async function persistProvider(): Promise<ProviderConfig | null> {
    setShowValidation(true);
    if (
      validation.formError ||
      Object.keys(validation.fieldErrors).length > 0
    ) {
      setNotice({
        tone: "bad",
        title: "Provider settings need attention",
        description:
          validation.formError ?? "Fix the highlighted fields before saving.",
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
        tone: "good",
        title: form.id ? "Provider updated" : "Provider created",
        description: `${saved.name} is ready for testing or agent routing.`,
      });
      onProviderSaved(saved);
      return saved;
    } catch (error) {
      setNotice({
        tone: "bad",
        title: "Could not save provider",
        description: getErrorMessage(error),
      });
      return null;
    } finally {
      setIsSaving(false);
    }
  }

  async function handleTestProvider() {
    setNotice(null);
    const provider =
      form.id && !isDirty
        ? (providers.find((entry) => entry.id === form.id) ?? null)
        : await persistProvider();
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
        tone: result.status === "ok" ? "good" : "bad",
        title:
          result.status === "ok"
            ? "Provider test passed"
            : "Provider test failed",
        description:
          result.preview ??
          result.error ??
          "The Control Plane did not return extra test output.",
      });
      onProviderSaved(result.provider);
    } catch (error) {
      setNotice({
        tone: "bad",
        title: "Could not test provider",
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
        tone: "good",
        title: "Provider deleted",
        description:
          "Agent references are not auto-rewritten, so review any agents that used this provider.",
      });
    } catch (error) {
      setNotice({
        tone: "bad",
        title: "Could not delete provider",
        description: getErrorMessage(error),
      });
    } finally {
      setConfirmDelete(false);
    }
  }

  const canSubmit = apiAvailable && !isSaving && !isTesting;
  const isSessionMode = form.secretMode === "session";
  const isEnvMode = form.secretMode === "env";
  const hasRuntimeSecret =
    form.secretMode === "none" ||
    form.hasSecret ||
    form.sessionSecret.trim().length > 0;

  return (
    <div className="page-stack">
      <PageHeader
        title="Providers"
        description="Configure model backends, secrets, and connection details that agents can route through."
        actions={
          <div className="button-row">
            <button
              className="button button--secondary"
              type="button"
              onClick={startNewProvider}
            >
              New provider
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
              : "Provider APIs unavailable"
          }
        >
          <p>{warning}</p>
        </InlineNotice>
      ) : null}

      <div className="page-grid page-grid--sidebar">
        <Panel
          title={`Configured providers (${providers.length})`}
          subtitle="Each provider stores a model default, a secret strategy, and its latest connectivity test."
        >
          <ProviderList
            providers={providers}
            selectedId={selectedId}
            onSelect={selectProvider}
            onStartNew={startNewProvider}
          />
        </Panel>

        <Panel
          title={form.id ? "Edit provider" : "New provider"}
          subtitle="Secrets remain write-only. Session secrets can be rotated by entering a new value before saving."
        >
          <ProviderForm
            form={form}
            catalog={catalog}
            currentSpec={currentSpec}
            apiAvailable={apiAvailable}
            showValidation={showValidation}
            validation={validation}
            isSaving={isSaving}
            isTesting={isTesting}
            canSubmit={canSubmit}
            confirmDelete={confirmDelete}
            notice={notice}
            isSessionMode={isSessionMode}
            isEnvMode={isEnvMode}
            hasRuntimeSecret={hasRuntimeSecret}
            onUpdateField={updateField}
            onProviderTypeChange={handleProviderTypeChange}
            onSave={persistProvider}
            onTest={handleTestProvider}
            onDelete={handleDeleteProvider}
          />
        </Panel>
      </div>
    </div>
  );
}
