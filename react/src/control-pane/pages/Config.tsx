import { useEffect, useState } from "react";
import { systemClient } from "../grpcClient";

export default function ConfigPage() {
  const [config, setConfig] = useState<any>(null);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    if (!systemClient) {
      setError("gRPC connection not initialized.");
      setLoading(false);
      return;
    }
    systemClient.getConfig({})
      .then((res: any) => {
        setConfig(res);
        setLoading(false);
      })
      .catch((err: any) => {
        console.error(err);
        setError("Failed to connect to backend: " + (err.message || String(err)));
        setLoading(false);
      });
  }, []);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await systemClient.updateConfig(config);
      alert("Configuration saved successfully!");
    } catch (err) {
      console.error(err);
      alert("Failed to save configuration.");
    } finally {
      setSaving(false);
    }
  };

  const handleChange = (field: string, value: string) => {
    setConfig((prev: any) => ({ ...prev, [field]: value }));
  };

  if (loading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "50vh" }}>
        <p style={{ color: "var(--text-secondary)" }}>Loading configuration...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "16px", maxWidth: "600px" }}>
        <h1 style={{ marginBottom: "8px" }}>AI Configuration</h1>
        <div className="glass-panel" style={{ padding: "24px", border: "1px solid #ef4444" }}>
          <p style={{ color: "#ef4444", fontWeight: 600, marginTop: 0 }}>Connection Error</p>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", marginBottom: 0 }}>{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="animate-fade-in">
      <h1 style={{ marginBottom: "8px" }}>AI Configuration</h1>
      <p style={{ color: "var(--text-secondary)", marginBottom: "32px" }}>Configure underlying AI models and orchestrator settings.</p>

      <form onSubmit={handleSave} style={{ maxWidth: "600px", display: "flex", flexDirection: "column", gap: "20px" }}>
        <div className="glass-panel" style={{ padding: "24px", display: "flex", flexDirection: "column", gap: "16px" }}>
          
          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            <label style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>LM Provider</label>
            <select 
              value={config.dspyLmProvider} 
              onChange={e => handleChange("dspyLmProvider", e.target.value)}
              style={{ padding: "10px", borderRadius: "8px", background: "var(--bg-primary)", color: "white", border: "1px solid var(--border-color)" }}
            >
              <option value="anthropic">Anthropic</option>
              <option value="openai">OpenAI</option>
              <option value="ollama">Ollama (Local)</option>
            </select>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            <label style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>LM Model</label>
            <input 
              type="text" 
              value={config.dspyLmModel} 
              onChange={e => handleChange("dspyLmModel", e.target.value)}
              placeholder="e.g. claude-3-5-sonnet-20241022"
              style={{ padding: "10px", borderRadius: "8px", background: "var(--bg-primary)", color: "white", border: "1px solid var(--border-color)" }}
            />
          </div>

        </div>

        <div className="glass-panel" style={{ padding: "24px", display: "flex", flexDirection: "column", gap: "16px" }}>
          <h3 style={{ fontSize: "1rem", marginBottom: "8px", marginTop: 0 }}>API Keys</h3>

          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            <label style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>Anthropic API Key</label>
            <input 
              type="password" 
              value={config.anthropicApiKey} 
              onChange={e => handleChange("anthropicApiKey", e.target.value)}
              style={{ padding: "10px", borderRadius: "8px", background: "var(--bg-primary)", color: "white", border: "1px solid var(--border-color)" }}
            />
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            <label style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>OpenAI API Key</label>
            <input 
              type="password" 
              value={config.openaiApiKey} 
              onChange={e => handleChange("openaiApiKey", e.target.value)}
              style={{ padding: "10px", borderRadius: "8px", background: "var(--bg-primary)", color: "white", border: "1px solid var(--border-color)" }}
            />
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            <label style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>Ollama Base URL</label>
            <input 
              type="text" 
              value={config.ollamaBaseUrl} 
              onChange={e => handleChange("ollamaBaseUrl", e.target.value)}
              placeholder="http://localhost:11434"
              style={{ padding: "10px", borderRadius: "8px", background: "var(--bg-primary)", color: "white", border: "1px solid var(--border-color)" }}
            />
          </div>
        </div>

        <div className="glass-panel" style={{ padding: "24px", display: "flex", flexDirection: "column", gap: "16px" }}>
          <h3 style={{ fontSize: "1rem", marginBottom: "8px", marginTop: 0 }}>System Settings</h3>

          <div style={{ display: "flex", gap: "16px" }}>
            <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "8px" }}>
              <label style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>Harness Port</label>
              <input 
                type="text" 
                value={config.harnessPort || ""} 
                onChange={e => handleChange("harnessPort", e.target.value)}
                style={{ padding: "10px", borderRadius: "8px", background: "var(--bg-primary)", color: "white", border: "1px solid var(--border-color)" }}
              />
            </div>
            <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "8px" }}>
              <label style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>Vite Port</label>
              <input 
                type="text" 
                value={config.vitePort || ""} 
                onChange={e => handleChange("vitePort", e.target.value)}
                style={{ padding: "10px", borderRadius: "8px", background: "var(--bg-primary)", color: "white", border: "1px solid var(--border-color)" }}
              />
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            <label style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>State DB File Path</label>
            <input 
              type="text" 
              value={config.stateDbPath || ""} 
              onChange={e => handleChange("stateDbPath", e.target.value)}
              style={{ padding: "10px", borderRadius: "8px", background: "var(--bg-primary)", color: "white", border: "1px solid var(--border-color)" }}
            />
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            <label style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>Logs Directory</label>
            <input 
              type="text" 
              value={config.logDir || ""} 
              onChange={e => handleChange("logDir", e.target.value)}
              style={{ padding: "10px", borderRadius: "8px", background: "var(--bg-primary)", color: "white", border: "1px solid var(--border-color)" }}
            />
          </div>
        </div>

        <button 
          type="submit" 
          disabled={saving}
          style={{
            background: "var(--accent-primary)",
            color: "white",
            padding: "12px 24px",
            borderRadius: "8px",
            fontWeight: 500,
            opacity: saving ? 0.7 : 1,
            marginTop: "8px",
            border: "none",
            cursor: "pointer"
          }}
        >
          {saving ? "Saving..." : "Save Configuration"}
        </button>
      </form>
    </div>
  );
}
