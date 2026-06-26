import type { AgentConfig, ProviderConfig } from "../../lib/api";

interface InputFormProps {
  agent: AgentConfig;
  inputs: Record<string, string>;
  showValidation: boolean;
  requiredErrors: Record<string, string>;
  providerMap: Map<string, ProviderConfig>;
  onChangeInput: (fieldName: string, value: string) => void;
}

function isLikelyMultiline(name: string, description: string): boolean {
  return /(text|context|notes|prompt|instructions|source|content|body)/i.test(
    `${name} ${description}`,
  );
}

export function InputForm({
  agent,
  inputs,
  showValidation,
  requiredErrors,
  providerMap,
  onChangeInput,
}: InputFormProps) {
  return (
    <div className="input-field-list">
      {agent.inputFields.map((field) => {
        const multiline = isLikelyMultiline(
          field.name,
          field.description ?? "",
        );
        return (
          <label className="field" key={field.name}>
            <span className="field__label">
              {field.label}
              {field.required ? " *" : ""}
            </span>
            {multiline ? (
              <textarea
                className="textarea"
                value={inputs[field.name] ?? ""}
                onChange={(event) =>
                  onChangeInput(field.name, event.target.value)
                }
                placeholder={field.description ?? ""}
                aria-invalid={Boolean(
                  showValidation && requiredErrors[field.name],
                )}
              />
            ) : (
              <input
                className="input"
                type="text"
                value={inputs[field.name] ?? ""}
                onChange={(event) =>
                  onChangeInput(field.name, event.target.value)
                }
                placeholder={field.description ?? ""}
                aria-invalid={Boolean(
                  showValidation && requiredErrors[field.name],
                )}
              />
            )}
            {field.description ? (
              <span className="field__hint">{field.description}</span>
            ) : null}
            {showValidation && requiredErrors[field.name] ? (
              <span className="field__error">{requiredErrors[field.name]}</span>
            ) : null}
          </label>
        );
      })}
    </div>
  );
}
