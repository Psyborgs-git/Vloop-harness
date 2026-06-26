import type { ProviderTypeSpec, SecretMode } from "../../lib/api";
import {
  InlineNotice,
  StatusBadge,
  cx,
  formatDateTime,
  formatRelativeTime,
} from "../../components/ui";
import type {
  ProviderFormState,
  ProviderValidation,
} from "./ProviderFormTypes";

interface ProviderFormProps {
  form: ProviderFormState;
  catalog: ProviderTypeSpec[];
  currentSpec: ProviderTypeSpec;
  apiAvailable: boolean;
  showValidation: boolean;
  validation: ProviderValidation;
  isSaving: boolean;
  isTesting: boolean;
  canSubmit: boolean;
  confirmDelete: boolean;
  notice: {
    tone: "good" | "warn" | "bad";
    title: string;
    description?: string;
  } | null;
  isSessionMode: boolean;
  isEnvMode: boolean;
  hasRuntimeSecret: boolean;
  onUpdateField: <K extends keyof ProviderFormState>(
    key: K,
    value: ProviderFormState[K],
  ) => void;
  onProviderTypeChange: (providerType: string) => void;
  onSave: () => void;
  onTest: () => void;
  onDelete: () => void;
}

export function ProviderForm({
  form,
  catalog,
  currentSpec,
  apiAvailable,
  showValidation,
  validation,
  isSaving,
  isTesting,
  canSubmit,
  confirmDelete,
  notice,
  isSessionMode,
  isEnvMode,
  hasRuntimeSecret,
  onUpdateField,
  onProviderTypeChange,
  onSave,
  onTest,
  onDelete,
}: ProviderFormProps) {
  return (
    <>
      {notice ? (
        <InlineNotice tone={notice.tone} title={notice.title}>
          {notice.description ? <p>{notice.description}</p> : null}
        </InlineNotice>
      ) : null}

      {!apiAvailable ? (
        <InlineNotice tone="warn" title="Read-only in this Control Plane build">
          <p>
            System status endpoints are present, but the provider CRUD routes
            under <code>/api/v1</code> are not available yet.
          </p>
        </InlineNotice>
      ) : null}

      <fieldset
        className="form-fieldset"
        disabled={!apiAvailable || isSaving || isTesting}
      >
        <div className="form-section">
          <label className="field">
            <span className="field__label">Provider type</span>
            <span
              className="segmented segmented--wrap"
              role="radiogroup"
              aria-label="Provider type"
            >
              {catalog.map((entry) => (
                <button
                  key={entry.key}
                  type="button"
                  className={cx(
                    "segmented__button",
                    form.providerType === entry.key && "is-active",
                  )}
                  onClick={() => onProviderTypeChange(entry.key)}
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
              <span>
                Default model: <code>{currentSpec.defaultModel}</code>
              </span>
              <span>Allowed secrets: {currentSpec.secretModes.join(", ")}</span>
            </div>
            {currentSpec.modelExamples.length > 0 ? (
              <p className="muted-text">
                Examples: {currentSpec.modelExamples.join(" · ")}
              </p>
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
              onChange={(event) => onUpdateField("name", event.target.value)}
              placeholder="e.g. Local Ollama"
              aria-invalid={Boolean(
                showValidation && validation.fieldErrors.name,
              )}
            />
            {showValidation && validation.fieldErrors.name ? (
              <span className="field__error">
                {validation.fieldErrors.name}
              </span>
            ) : null}
          </label>

          <label className="field field--checkbox">
            <span className="field__label">Enabled</span>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={form.enabled}
                onChange={(event) =>
                  onUpdateField("enabled", event.target.checked)
                }
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
              onChange={(event) =>
                onUpdateField("defaultModel", event.target.value)
              }
              placeholder={currentSpec.defaultModel}
              aria-invalid={Boolean(
                showValidation && validation.fieldErrors.defaultModel,
              )}
            />
            {showValidation && validation.fieldErrors.defaultModel ? (
              <span className="field__error">
                {validation.fieldErrors.defaultModel}
              </span>
            ) : null}
          </label>

          <label className="field">
            <span className="field__label">API base</span>
            <input
              className="input mono"
              type="text"
              value={form.apiBase}
              onChange={(event) => onUpdateField("apiBase", event.target.value)}
              placeholder={currentSpec.apiBaseHint ?? "Optional"}
              aria-invalid={Boolean(
                showValidation && validation.fieldErrors.apiBase,
              )}
            />
            {currentSpec.apiBaseHint ? (
              <span className="field__hint">
                Suggested: {currentSpec.apiBaseHint}
              </span>
            ) : null}
            {showValidation && validation.fieldErrors.apiBase ? (
              <span className="field__error">
                {validation.fieldErrors.apiBase}
              </span>
            ) : null}
          </label>
        </div>

        <div className="form-grid form-grid--two">
          <label className="field">
            <span className="field__label">API version</span>
            <input
              className="input mono"
              type="text"
              value={form.apiVersion}
              onChange={(event) =>
                onUpdateField("apiVersion", event.target.value)
              }
              placeholder={currentSpec.apiVersionHint ?? "Optional"}
            />
          </label>

          <label className="field">
            <span className="field__label">Organization</span>
            <input
              className="input"
              type="text"
              value={form.organization}
              onChange={(event) =>
                onUpdateField("organization", event.target.value)
              }
              placeholder="Optional org or project identifier"
            />
          </label>
        </div>

        <div className="form-section">
          <label className="field">
            <span className="field__label">Secret mode</span>
            <span
              className="segmented"
              role="radiogroup"
              aria-label="Secret mode"
            >
              {currentSpec.secretModes.map((mode) => (
                <button
                  key={mode}
                  type="button"
                  className={cx(
                    "segmented__button",
                    form.secretMode === mode && "is-active",
                  )}
                  onClick={() =>
                    onUpdateField("secretMode", mode as SecretMode)
                  }
                >
                  {mode}
                </button>
              ))}
            </span>
            {showValidation && validation.fieldErrors.secretMode ? (
              <span className="field__error">
                {validation.fieldErrors.secretMode}
              </span>
            ) : null}
          </label>

          {isEnvMode ? (
            <label className="field">
              <span className="field__label">Environment variable name</span>
              <input
                className="input mono"
                type="text"
                value={form.secretEnvVar}
                onChange={(event) =>
                  onUpdateField("secretEnvVar", event.target.value)
                }
                placeholder="OPENAI_API_KEY"
                aria-invalid={Boolean(
                  showValidation && validation.fieldErrors.secretEnvVar,
                )}
              />
              <span className="field__hint">
                The Control Plane reads this value from its own process
                environment at runtime.
              </span>
              {showValidation && validation.fieldErrors.secretEnvVar ? (
                <span className="field__error">
                  {validation.fieldErrors.secretEnvVar}
                </span>
              ) : null}
            </label>
          ) : null}

          {isSessionMode ? (
            <label className="field">
              <span className="field__label">Session secret</span>
              <input
                className="input"
                type="password"
                value={form.sessionSecret}
                onChange={(event) =>
                  onUpdateField("sessionSecret", event.target.value)
                }
                placeholder={
                  form.hasSecret
                    ? "Enter a new secret to rotate it"
                    : "Enter a session secret"
                }
                aria-invalid={Boolean(
                  showValidation && validation.fieldErrors.sessionSecret,
                )}
              />
              <span className="field__hint">
                Write-only. The current value is never read back into the UI.
              </span>
              {showValidation && validation.fieldErrors.sessionSecret ? (
                <span className="field__error">
                  {validation.fieldErrors.sessionSecret}
                </span>
              ) : null}
            </label>
          ) : null}

          <div className="status-strip">
            <StatusBadge
              status={hasRuntimeSecret ? "ready" : "pending"}
              label={hasRuntimeSecret ? "Secret available" : "Secret missing"}
              tone={hasRuntimeSecret ? "good" : "warn"}
            />
            <StatusBadge
              status={form.lastTestStatus}
              label={
                form.lastTestStatus === "unknown" ? "Not tested yet" : undefined
              }
            />
            {form.lastTestedAt ? (
              <span className="muted-text">
                Tested {formatRelativeTime(form.lastTestedAt)}
              </span>
            ) : null}
          </div>
          {form.lastTestError ? (
            <p className="field__error">
              Last test error: {form.lastTestError}
            </p>
          ) : null}
        </div>
      </fieldset>

      <div className="editor-footer">
        <div className="editor-footer__meta">
          <span>
            Updated {form.updatedAt ? formatDateTime(form.updatedAt) : "—"}
          </span>
          {form.revision > 0 ? <span>Revision {form.revision}</span> : null}
        </div>
        <div className="button-row">
          <button
            className="button button--secondary"
            type="button"
            onClick={onTest}
            disabled={!canSubmit}
          >
            {isTesting ? "Testing…" : "Test provider"}
          </button>
          <button
            className="button button--danger"
            type="button"
            onClick={onDelete}
            disabled={!apiAvailable || isSaving || isTesting}
          >
            {form.id
              ? confirmDelete
                ? "Confirm delete"
                : "Delete provider"
              : "Discard draft"}
          </button>
          <button
            className="button button--primary"
            type="button"
            onClick={() => {
              void onSave();
            }}
            disabled={!canSubmit}
          >
            {isSaving ? "Saving…" : "Save provider"}
          </button>
        </div>
      </div>
    </>
  );
}
