import type { AgentTemplate, ProviderConfig } from "../../lib/api";
import {
  InlineNotice,
  JsonBlock,
  StatusBadge,
  cx,
  formatDateTime,
  formatRelativeTime,
} from "../../components/ui";
import type {
  AgentFieldState,
  AgentFormState,
  AgentValidationState,
} from "./AgentFormTypes";

interface AgentFormProps {
  form: AgentFormState;
  providers: ProviderConfig[];
  agentTemplates: AgentTemplate[];
  apiAvailable: boolean;
  templateId: string;
  showValidation: boolean;
  validation: AgentValidationState;
  isSaving: boolean;
  isValidating: boolean;
  canSubmit: boolean;
  confirmDelete: boolean;
  notice: {
    tone: "good" | "warn" | "bad";
    title: string;
    description?: string;
  } | null;
  onTemplateChange: (id: string) => void;
  onApplyTemplate: () => void;
  onUpdateField: <K extends keyof AgentFormState>(
    key: K,
    value: AgentFormState[K],
  ) => void;
  onUpdateName: (value: string) => void;
  onUpdateSlug: (value: string) => void;
  onUpdateFieldRow: (
    fieldId: string,
    patch: Partial<Omit<AgentFieldState, "id">>,
  ) => void;
  onAddInputField: () => void;
  onRemoveInputField: (fieldId: string) => void;
  onUpdateOutputMode: (mode: "text" | "json") => void;
  onValidate: () => void;
  onSave: () => void;
  onDelete: () => void;
  onOpenPlayground?: (agentId: string) => void;
}

export function AgentForm({
  form,
  providers,
  agentTemplates,
  apiAvailable,
  templateId,
  showValidation,
  validation,
  isSaving,
  isValidating,
  canSubmit,
  confirmDelete,
  notice,
  onTemplateChange,
  onApplyTemplate,
  onUpdateField,
  onUpdateName,
  onUpdateSlug,
  onUpdateFieldRow,
  onAddInputField,
  onRemoveInputField,
  onUpdateOutputMode,
  onValidate,
  onSave,
  onDelete,
  onOpenPlayground,
}: AgentFormProps) {
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
            System status endpoints are present, but the agent CRUD routes under{" "}
            <code>/api/v1</code> are not available yet.
          </p>
        </InlineNotice>
      ) : null}

      <fieldset
        className="form-fieldset"
        disabled={!apiAvailable || !canSubmit || isSaving || isValidating}
      >
        <div className="form-section form-section--inline">
          <label className="field field--grow">
            <span className="field__label">Template</span>
            <select
              className="select"
              value={templateId}
              onChange={(event) => onTemplateChange(event.target.value)}
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
            onClick={onApplyTemplate}
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
              onChange={(event) => onUpdateName(event.target.value)}
              placeholder="e.g. Release-note summarizer"
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

          <label className="field">
            <span className="field__label">Slug</span>
            <input
              className="input mono"
              type="text"
              value={form.slug}
              onChange={(event) => onUpdateSlug(event.target.value)}
              placeholder="release-note-summarizer"
              aria-invalid={Boolean(
                showValidation && validation.fieldErrors.slug,
              )}
            />
            {showValidation && validation.fieldErrors.slug ? (
              <span className="field__error">
                {validation.fieldErrors.slug}
              </span>
            ) : null}
          </label>
        </div>

        <div className="form-grid form-grid--two">
          <label className="field">
            <span className="field__label">Description</span>
            <input
              className="input"
              type="text"
              value={form.description}
              onChange={(event) =>
                onUpdateField("description", event.target.value)
              }
              placeholder="Short summary shown in the list and playground"
            />
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
              <span>Allow the playground to run this agent.</span>
            </label>
          </label>
        </div>

        <label className="field">
          <span className="field__label">Instructions</span>
          <textarea
            className="textarea textarea--lg"
            value={form.instructions}
            onChange={(event) =>
              onUpdateField("instructions", event.target.value)
            }
            placeholder="Describe how the agent should behave, what to prioritize, and how to format its response."
            aria-invalid={Boolean(
              showValidation && validation.fieldErrors.instructions,
            )}
          />
          {showValidation && validation.fieldErrors.instructions ? (
            <span className="field__error">
              {validation.fieldErrors.instructions}
            </span>
          ) : null}
        </label>

        <div className="form-grid form-grid--two">
          <label className="field">
            <span className="field__label">Reasoning mode</span>
            <span
              className="segmented"
              role="radiogroup"
              aria-label="Reasoning mode"
            >
              {["predict", "chain_of_thought"].map((mode) => (
                <button
                  key={mode}
                  type="button"
                  className={cx(
                    "segmented__button",
                    form.reasoningMode === mode && "is-active",
                  )}
                  onClick={() =>
                    onUpdateField(
                      "reasoningMode",
                      mode as "predict" | "chain_of_thought",
                    )
                  }
                >
                  {mode === "chain_of_thought" ? "chain_of_thought" : "predict"}
                </button>
              ))}
            </span>
          </label>

          <label className="field">
            <span className="field__label">Default provider</span>
            <select
              className="select"
              value={form.defaultProviderId}
              onChange={(event) =>
                onUpdateField("defaultProviderId", event.target.value)
              }
              aria-invalid={Boolean(
                showValidation && validation.fieldErrors.defaultProviderId,
              )}
            >
              <option value="">Select a provider</option>
              {providers.map((provider) => (
                <option key={provider.id} value={provider.id}>
                  {provider.name}
                </option>
              ))}
            </select>
            {showValidation && validation.fieldErrors.defaultProviderId ? (
              <span className="field__error">
                {validation.fieldErrors.defaultProviderId}
              </span>
            ) : null}
          </label>
        </div>

        <div className="form-section">
          <div className="section-header-row">
            <div>
              <h3>Input fields</h3>
              <p>These fields render the playground form automatically.</p>
            </div>
            <button
              className="button button--secondary"
              type="button"
              onClick={onAddInputField}
            >
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
                      onChange={(event) =>
                        onUpdateFieldRow(field.id, { name: event.target.value })
                      }
                      placeholder="source_text"
                      aria-invalid={Boolean(
                        showValidation &&
                        validation.fieldErrors[`field-name-${field.id}`],
                      )}
                    />
                    {showValidation &&
                    validation.fieldErrors[`field-name-${field.id}`] ? (
                      <span className="field__error">
                        {validation.fieldErrors[`field-name-${field.id}`]}
                      </span>
                    ) : null}
                  </label>
                  <label className="field">
                    <span className="field__label">Label</span>
                    <input
                      className="input"
                      type="text"
                      value={field.label}
                      onChange={(event) =>
                        onUpdateFieldRow(field.id, {
                          label: event.target.value,
                        })
                      }
                      placeholder="Source text"
                      aria-invalid={Boolean(
                        showValidation &&
                        validation.fieldErrors[`field-label-${field.id}`],
                      )}
                    />
                    {showValidation &&
                    validation.fieldErrors[`field-label-${field.id}`] ? (
                      <span className="field__error">
                        {validation.fieldErrors[`field-label-${field.id}`]}
                      </span>
                    ) : null}
                  </label>
                  <label className="field field--checkbox">
                    <span className="field__label">Required</span>
                    <label className="checkbox-row">
                      <input
                        type="checkbox"
                        checked={field.required}
                        onChange={(event) =>
                          onUpdateFieldRow(field.id, {
                            required: event.target.checked,
                          })
                        }
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
                    value={field.description ?? ""}
                    onChange={(event) =>
                      onUpdateFieldRow(field.id, {
                        description: event.target.value,
                      })
                    }
                    placeholder="Shown under the field in the playground"
                  />
                </label>
                <div className="button-row button-row--end">
                  <button
                    className="button button--quiet"
                    type="button"
                    onClick={() => onRemoveInputField(field.id)}
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
              <p>
                Text outputs render directly. JSON outputs must return a
                top-level object.
              </p>
            </div>
          </div>
          <div className="form-grid form-grid--two">
            <label className="field">
              <span className="field__label">Output mode</span>
              <span
                className="segmented"
                role="radiogroup"
                aria-label="Output mode"
              >
                {["text", "json"].map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    className={cx(
                      "segmented__button",
                      form.outputMode === mode && "is-active",
                    )}
                    onClick={() => onUpdateOutputMode(mode as "text" | "json")}
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
                onChange={(event) =>
                  onUpdateField("outputFieldName", event.target.value)
                }
                placeholder="response"
                aria-invalid={Boolean(
                  showValidation && validation.fieldErrors.outputFieldName,
                )}
              />
              {showValidation && validation.fieldErrors.outputFieldName ? (
                <span className="field__error">
                  {validation.fieldErrors.outputFieldName}
                </span>
              ) : null}
            </label>
          </div>

          {form.outputMode === "json" ? (
            <label className="field">
              <span className="field__label">Output schema (JSON object)</span>
              <textarea
                className="textarea textarea--lg mono"
                value={form.outputSchemaText}
                onChange={(event) =>
                  onUpdateField("outputSchemaText", event.target.value)
                }
                placeholder='{"theme": "string", "next_actions": ["string"]}'
                aria-invalid={Boolean(
                  showValidation && validation.fieldErrors.outputSchemaText,
                )}
              />
              {showValidation && validation.fieldErrors.outputSchemaText ? (
                <span className="field__error">
                  {validation.fieldErrors.outputSchemaText}
                </span>
              ) : null}
            </label>
          ) : null}
        </div>

        <div className="form-section">
          <div className="section-header-row">
            <div>
              <h3>Runtime defaults</h3>
              <p>
                These values can still be overridden per run in the playground.
              </p>
            </div>
          </div>
          <div className="form-grid form-grid--two">
            <label className="field">
              <span className="field__label">Model override</span>
              <input
                className="input mono"
                type="text"
                value={form.modelOverride}
                onChange={(event) =>
                  onUpdateField("modelOverride", event.target.value)
                }
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
                onChange={(event) =>
                  onUpdateField("temperature", event.target.value)
                }
                aria-invalid={Boolean(
                  showValidation && validation.fieldErrors.temperature,
                )}
              />
              {showValidation && validation.fieldErrors.temperature ? (
                <span className="field__error">
                  {validation.fieldErrors.temperature}
                </span>
              ) : null}
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
                onChange={(event) =>
                  onUpdateField("maxTokens", event.target.value)
                }
                aria-invalid={Boolean(
                  showValidation && validation.fieldErrors.maxTokens,
                )}
              />
              {showValidation && validation.fieldErrors.maxTokens ? (
                <span className="field__error">
                  {validation.fieldErrors.maxTokens}
                </span>
              ) : null}
            </label>
          </div>
        </div>
      </fieldset>

      {form.outputMode === "json" && validation.parsedOutputSchema ? (
        <details className="details-block" open>
          <summary>Parsed output schema preview</summary>
          <JsonBlock value={validation.parsedOutputSchema} />
        </details>
      ) : null}

      <div className="editor-footer">
        <div className="editor-footer__meta">
          <span>
            Updated {form.updatedAt ? formatDateTime(form.updatedAt) : "—"}
          </span>
          {form.revision > 0 ? <span>Revision {form.revision}</span> : null}
          {form.createdAt ? (
            <span>Created {formatRelativeTime(form.createdAt)}</span>
          ) : null}
        </div>
        <div className="button-row">
          <button
            className="button button--secondary"
            type="button"
            onClick={() => {
              void onValidate();
            }}
            disabled={!canSubmit}
          >
            {isValidating ? "Validating…" : "Validate"}
          </button>
          <button
            className="button button--danger"
            type="button"
            onClick={() => {
              void onDelete();
            }}
            disabled={!apiAvailable || isSaving || isValidating}
          >
            {form.id
              ? confirmDelete
                ? "Confirm delete"
                : "Delete agent"
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
            {isSaving ? "Saving…" : "Save agent"}
          </button>
        </div>
      </div>
    </>
  );
}
