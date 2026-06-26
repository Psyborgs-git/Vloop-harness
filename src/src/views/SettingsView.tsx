import { useCallback, useEffect, useState } from "react";
import {
  getDatabaseSettings,
  getErrorMessage,
  saveDatabaseSettings,
  testDatabaseConnection,
  type DatabaseSettings,
} from "../lib/api";
import {
  EmptyState,
  InlineNotice,
  PageHeader,
  Panel,
  StatusBadge,
} from "../components/ui";

interface SettingsViewProps {
  apiAvailable: boolean;
}

const BACKEND_OPTIONS = [
  { value: "", label: "SQLite (default)", hint: "~/.vloop/data/control-plane.db" },
  {
    value: "postgresql://user:pass@localhost:5432/vloop",
    label: "PostgreSQL",
    hint: "Full PostgreSQL with pgvector support",
  },
  {
    value: "duckdb://~/.vloop/data/control-plane.duckdb",
    label: "DuckDB",
    hint: "File-based OLAP engine, great for analytics",
  },
];

const VECTOR_OPTIONS = [
  { value: "", label: "None (disabled)", hint: "No vector search capabilities" },
  {
    value: "postgresql://user:pass@localhost:5432/vloop",
    label: "pgvector (PostgreSQL)",
    hint: "Requires PostgreSQL with pgvector extension",
  },
  {
    value: "duckdb://~/.vloop/data/vectors.duckdb",
    label: "DuckDB arrays",
    hint: "Cosine similarity on FLOAT[] arrays",
  },
  {
    value: "pinecone://",
    label: "Pinecone (cloud)",
    hint: "Requires PINECONE_API_KEY and PINECONE_ENVIRONMENT",
  },
];

export function SettingsView({ apiAvailable }: SettingsViewProps) {
  const [settings, setSettings] = useState<DatabaseSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dbUrl, setDbUrl] = useState("");
  const [vecUrl, setVecUrl] = useState("");
  const [testResult, setTestResult] = useState<{
    ok: boolean;
    message: string;
  } | null>(null);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveResult, setSaveResult] = useState<string | null>(null);

  const fetchSettings = useCallback(async () => {
    if (!apiAvailable) return;
    setLoading(true);
    try {
      const s = await getDatabaseSettings();
      setSettings(s);
      setDbUrl(s.databaseUrl || "");
      setVecUrl(s.vectorDbUrl || "");
      setError(null);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [apiAvailable]);

  useEffect(() => {
    void fetchSettings();
  }, [fetchSettings]);

  async function handleTestConnection() {
    if (!dbUrl.trim()) return;
    setTesting(true);
    setTestResult(null);
    try {
      const result = await testDatabaseConnection(dbUrl.trim());
      setTestResult(result);
    } catch (err) {
      setTestResult({ ok: false, message: getErrorMessage(err) });
    } finally {
      setTesting(false);
    }
  }

  async function handleSave() {
    setSaving(true);
    setSaveResult(null);
    try {
      const result = await saveDatabaseSettings({
        databaseUrl: dbUrl.trim(),
        vectorDbUrl: vecUrl.trim(),
      });
      setSaveResult(result.message);
    } catch (err) {
      setSaveResult(`Failed to save: ${getErrorMessage(err)}`);
    } finally {
      setSaving(false);
    }
  }

  if (!apiAvailable) {
    return (
      <div className="page-stack">
        <PageHeader
          title="Settings"
          description="Database and vector store configuration."
        />
        <InlineNotice tone="warn" title="Settings API unavailable">
          <p>
            The settings API is not available in this control plane build.
            Use environment variables to configure the database:
            <code>VLOOP_DATABASE_URL</code> and <code>VLOOP_VECTOR_DB_URL</code>.
          </p>
        </InlineNotice>
      </div>
    );
  }

  return (
    <div className="page-stack">
      <PageHeader
        title="Settings"
        description="Configure the database backend and vector store for data persistence."
        actions={
          <div className="button-row">
            <button
              className="button button--secondary"
              type="button"
              onClick={() => {
                void fetchSettings();
              }}
              disabled={loading}
            >
              {loading ? "Loading…" : "Refresh"}
            </button>
          </div>
        }
      />

      {error ? (
        <InlineNotice tone="bad" title="Could not load settings">
          <p>{error}</p>
        </InlineNotice>
      ) : null}

      {settings ? (
        <>
          <Panel
            title="Active backends"
            subtitle="The currently configured database and vector store."
          >
            <div className="key-value-grid">
              <div className="key-value-item">
                <span className="key-value-item__label">Database backend</span>
                <span className="key-value-item__value">
                  <StatusBadge
                    tone="accent"
                    label={settings.activeBackend || "Unknown"}
                  />
                </span>
              </div>
              <div className="key-value-item">
                <span className="key-value-item__label">Vector store</span>
                <span className="key-value-item__value">
                  <StatusBadge
                    tone={
                      settings.vectorStoreActive === "none" ? "neutral" : "accent"
                    }
                    label={
                      settings.vectorStoreActive === "none"
                        ? "Disabled"
                        : settings.vectorStoreActive
                    }
                  />
                </span>
              </div>
            </div>
          </Panel>

          <Panel
            title="Database configuration"
            subtitle="Change the database backend and vector store. Changes take effect after restart."
          >
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <label className="field">
                <span className="field__label">Database URL</span>
                <span className="field__hint">
                  Connection URL for the database backend. Leave empty for default
                  SQLite.
                </span>
                <select
                  className="select"
                  value={dbUrl}
                  onChange={(e) => setDbUrl(e.target.value)}
                >
                  {BACKEND_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
                <input
                  className="input"
                  type="text"
                  value={dbUrl}
                  onChange={(e) => setDbUrl(e.target.value)}
                  placeholder="postgresql://user:pass@localhost:5432/vloop"
                  style={{ marginTop: 8 }}
                />
              </label>

              <label className="field">
                <span className="field__label">Vector DB URL</span>
                <span className="field__hint">
                  Separate connection URL for the vector store. Leave empty to
                  disable vector features.
                </span>
                <select
                  className="select"
                  value={vecUrl}
                  onChange={(e) => setVecUrl(e.target.value)}
                >
                  {VECTOR_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
                <input
                  className="input"
                  type="text"
                  value={vecUrl}
                  onChange={(e) => setVecUrl(e.target.value)}
                  placeholder="pinecone:// or duckdb://..."
                  style={{ marginTop: 8 }}
                />
              </label>

              <div className="button-row" style={{ gap: 12 }}>
                <button
                  className="button button--secondary"
                  type="button"
                  onClick={() => {
                    void handleTestConnection();
                  }}
                  disabled={testing || !dbUrl.trim()}
                >
                  {testing ? "Testing…" : "Test connection"}
                </button>
                <button
                  className="button button--primary"
                  type="button"
                  onClick={() => {
                    void handleSave();
                  }}
                  disabled={saving}
                >
                  {saving ? "Saving…" : "Save & apply on restart"}
                </button>
              </div>

              {testResult ? (
                <InlineNotice
                  tone={testResult.ok ? "good" : "bad"}
                  title={testResult.ok ? "Connection OK" : "Connection failed"}
                >
                  <p>{testResult.message}</p>
                </InlineNotice>
              ) : null}

              {saveResult ? (
                <InlineNotice tone="accent" title="Settings saved">
                  <p>{saveResult}</p>
                </InlineNotice>
              ) : null}
            </div>
          </Panel>

          <Panel
            title="Environment variables"
            subtitle="These variables can also be set in your shell before starting the control plane."
          >
            <div className="key-value-grid">
              <div className="key-value-item">
                <span className="key-value-item__label">
                  <code>VLOOP_DATABASE_URL</code>
                </span>
                <span className="key-value-item__value">
                  {settings.databaseUrl || "(not set, using SQLite fallback)"}
                </span>
              </div>
              <div className="key-value-item">
                <span className="key-value-item__label">
                  <code>VLOOP_VECTOR_DB_URL</code>
                </span>
                <span className="key-value-item__value">
                  {settings.vectorDbUrl || "(not set, vector features disabled)"}
                </span>
              </div>
              <div className="key-value-item">
                <span className="key-value-item__label">
                  <code>PINECONE_API_KEY</code>
                </span>
                <span className="key-value-item__value">
                  Required for Pinecone vector store
                </span>
              </div>
              <div className="key-value-item">
                <span className="key-value-item__label">
                  <code>PINECONE_ENVIRONMENT</code>
                </span>
                <span className="key-value-item__value">
                  Default: us-west1-gcp
                </span>
              </div>
            </div>
          </Panel>
        </>
      ) : loading ? (
        <EmptyState title="Loading settings…" description="Fetching configuration from the control plane." />
      ) : null}
    </div>
  );
}
