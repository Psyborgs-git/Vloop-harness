import { useEffect, useState } from "react";
import { environmentClient } from "../grpcClient";
import { EnvironmentType } from "../../gen/environment_pb";
import { Edit2, Trash2, Plus, Terminal, Cpu, Globe, Folder, Box } from "lucide-react";

export default function EnvironmentsPage() {
  const [environments, setEnvironments] = useState<any[]>([]);
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [editingEnv, setEditingEnv] = useState<any | null>(null);

  // Form states
  const [envName, setEnvName] = useState("");
  const [envDescription, setEnvDescription] = useState("");
  const [envType, setEnvType] = useState<EnvironmentType>(EnvironmentType.LOCAL);
  const [envImage, setEnvImage] = useState("");
  const [envHost, setEnvHost] = useState("");
  const [envUser, setEnvUser] = useState("");
  const [envExtraConfig, setEnvExtraConfig] = useState("{}");
  const [envPath, setEnvPath] = useState("");
  const [envPythonPath, setEnvPythonPath] = useState("");
  const [envSshKey, setEnvSshKey] = useState("");

  const fetchEnvironments = async () => {
    try {
      const res = await environmentClient.listEnvironments({});
      setEnvironments(res.environments);
    } catch (e) {
      console.error("Failed to fetch environments", e);
    }
  };

  useEffect(() => {
    fetchEnvironments();
  }, []);

  const resetForm = () => {
    setEnvName("");
    setEnvDescription("");
    setEnvType(EnvironmentType.LOCAL);
    setEnvImage("");
    setEnvHost("");
    setEnvUser("");
    setEnvExtraConfig("{}");
    setEnvPath("");
    setEnvPythonPath("");
    setEnvSshKey("");
    setEditingEnv(null);
  };

  const handleEditClick = (env: any) => {
    setEditingEnv(env);
    setEnvName(env.name);
    setEnvDescription(env.description);
    setEnvType(env.config?.type ?? EnvironmentType.LOCAL);
    setEnvImage(env.config?.image ?? "");
    setEnvHost(env.config?.host ?? "");
    setEnvUser(env.config?.user ?? "");
    setEnvExtraConfig(env.config?.extraConfig ?? "{}");
    setEnvPath(env.config?.path ?? "");
    setEnvPythonPath(env.config?.pythonPath ?? "");
    setEnvSshKey(env.config?.sshKey ?? "");
    setIsFormOpen(true);
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const payload = {
        name: envName || "Unnamed Environment",
        description: envDescription,
        config: {
          type: envType,
          image: envType === EnvironmentType.DOCKER ? envImage : "",
          host: envType === EnvironmentType.SSH ? envHost : "",
          user: envType === EnvironmentType.SSH ? envUser : "",
          extraConfig: envExtraConfig,
          path: envPath,
          pythonPath: envType === EnvironmentType.PYTHON ? envPythonPath : "",
          sshKey: envType === EnvironmentType.SSH ? envSshKey : "",
        }
      };

      if (editingEnv) {
        await environmentClient.updateEnvironment({
          id: editingEnv.id,
          ...payload
        });
      } else {
        await environmentClient.createEnvironment(payload);
      }

      setIsFormOpen(false);
      resetForm();
      fetchEnvironments();
    } catch (e) {
      console.error("Failed to save environment", e);
      alert("Failed to save environment. Check console for details.");
    }
  };

  const handleDelete = async (id: string) => {
    if (confirm("Are you sure you want to delete this environment?")) {
      try {
        await environmentClient.deleteEnvironment({ id });
        fetchEnvironments();
      } catch (e: any) {
        console.error("Failed to delete environment", e);
        alert(e.message || "Failed to delete environment.");
      }
    }
  };

  const getEnvIcon = (type: EnvironmentType) => {
    switch (type) {
      case EnvironmentType.LOCAL:
        return <Cpu size={18} className="text-indigo-400" style={{ color: "#6366f1" }} />;
      case EnvironmentType.DOCKER:
        return <Box size={18} className="text-sky-400" style={{ color: "#38bdf8" }} />;
      case EnvironmentType.SSH:
        return <Globe size={18} className="text-emerald-400" style={{ color: "#34d399" }} />;
      case EnvironmentType.PYTHON:
        return <Terminal size={18} className="text-amber-400" style={{ color: "#fbbf24" }} />;
      default:
        return <Cpu size={18} />;
    }
  };

  const getTypeName = (type: EnvironmentType) => {
    switch (type) {
      case EnvironmentType.LOCAL: return "Local Machine";
      case EnvironmentType.DOCKER: return "Docker Container";
      case EnvironmentType.SSH: return "Remote SSH Host";
      case EnvironmentType.PYTHON: return "Python Virtualenv";
      default: return "Unknown";
    }
  };

  return (
    <div className="animate-fade-in">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "32px" }}>
        <div>
          <h1 style={{ marginBottom: "8px" }}>Execution Environments</h1>
          <p style={{ color: "var(--text-secondary)", margin: 0 }}>Configure sandboxes, Python environments, and SSH connections for processes.</p>
        </div>
        <button 
          onClick={() => { resetForm(); setIsFormOpen(true); }}
          style={{
            padding: "10px 18px",
            backgroundColor: "var(--accent-primary)",
            color: "#fff",
            border: "none",
            borderRadius: "8px",
            cursor: "pointer",
            fontWeight: 500,
            display: "flex",
            alignItems: "center",
            gap: "8px",
            boxShadow: "var(--shadow-glow)"
          }}
        >
          <Plus size={18} /> New Environment
        </button>
      </div>

      {isFormOpen && (
        <div className="glass-panel" style={{ padding: "28px", marginBottom: "32px", borderRadius: "16px" }}>
          <h3 style={{ marginTop: 0, marginBottom: "20px", fontSize: "1.2rem", fontWeight: 600 }}>
            {editingEnv ? `Edit Environment: ${editingEnv.name}` : "Create New Environment"}
          </h3>
          <form onSubmit={handleSave} style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
            <div style={{ display: "flex", gap: "20px" }}>
              <div style={{ flex: 1 }}>
                <label style={{ display: "block", marginBottom: "6px", fontSize: "0.875rem", color: "var(--text-secondary)" }}>Name</label>
                <input 
                  type="text" 
                  value={envName} 
                  required
                  onChange={(e) => setEnvName(e.target.value)} 
                  placeholder="e.g. Local Python 3.11, Production Server"
                  style={{ width: "100%", padding: "10px", borderRadius: "6px", border: "1px solid var(--border-color)", backgroundColor: "var(--bg-primary)", color: "var(--text-primary)" }}
                />
              </div>
              <div style={{ flex: 1 }}>
                <label style={{ display: "block", marginBottom: "6px", fontSize: "0.875rem", color: "var(--text-secondary)" }}>Environment Type</label>
                <select 
                  value={envType} 
                  onChange={(e) => setEnvType(Number(e.target.value))}
                  style={{ width: "100%", padding: "10px", borderRadius: "6px", border: "1px solid var(--border-color)", backgroundColor: "var(--bg-primary)", color: "var(--text-primary)" }}
                >
                  <option value={EnvironmentType.LOCAL}>Local Machine</option>
                  <option value={EnvironmentType.PYTHON}>Python Local Virtualenv</option>
                  <option value={EnvironmentType.DOCKER}>Docker Container</option>
                  <option value={EnvironmentType.SSH}>Remote SSH Host</option>
                </select>
              </div>
            </div>

            <div>
              <label style={{ display: "block", marginBottom: "6px", fontSize: "0.875rem", color: "var(--text-secondary)" }}>Description</label>
              <input 
                type="text" 
                value={envDescription} 
                onChange={(e) => setEnvDescription(e.target.value)} 
                placeholder="Brief details about what this environment is for"
                style={{ width: "100%", padding: "10px", borderRadius: "6px", border: "1px solid var(--border-color)", backgroundColor: "var(--bg-primary)", color: "var(--text-primary)" }}
              />
            </div>

            <div style={{ display: "flex", gap: "20px" }}>
              <div style={{ flex: 1 }}>
                <label style={{ display: "block", marginBottom: "6px", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
                  Environment Path / Working Directory <span style={{ fontSize: "0.75rem", color: "var(--text-tertiary)" }}>(Optional override)</span>
                </label>
                <input 
                  type="text" 
                  value={envPath} 
                  onChange={(e) => setEnvPath(e.target.value)} 
                  placeholder="e.g. /Users/name/projects/my-app, /var/www/app"
                  style={{ width: "100%", padding: "10px", borderRadius: "6px", border: "1px solid var(--border-color)", backgroundColor: "var(--bg-primary)", color: "var(--text-primary)" }}
                />
              </div>

              {envType === EnvironmentType.PYTHON && (
                <div style={{ flex: 1 }}>
                  <label style={{ display: "block", marginBottom: "6px", fontSize: "0.875rem", color: "var(--text-secondary)" }}>Python Virtualenv Root Path</label>
                  <input 
                    type="text" 
                    value={envPythonPath} 
                    required
                    onChange={(e) => setEnvPythonPath(e.target.value)} 
                    placeholder="e.g. /Users/name/projects/my-app/.venv"
                    style={{ width: "100%", padding: "10px", borderRadius: "6px", border: "1px solid var(--border-color)", backgroundColor: "var(--bg-primary)", color: "var(--text-primary)" }}
                  />
                </div>
              )}

              {envType === EnvironmentType.DOCKER && (
                <div style={{ flex: 1 }}>
                  <label style={{ display: "block", marginBottom: "6px", fontSize: "0.875rem", color: "var(--text-secondary)" }}>Docker Image</label>
                  <input 
                    type="text" 
                    value={envImage} 
                    required
                    onChange={(e) => setEnvImage(e.target.value)} 
                    placeholder="e.g. ubuntu:latest, python:3.10-slim"
                    style={{ width: "100%", padding: "10px", borderRadius: "6px", border: "1px solid var(--border-color)", backgroundColor: "var(--bg-primary)", color: "var(--text-primary)" }}
                  />
                </div>
              )}
            </div>

            {envType === EnvironmentType.SSH && (
              <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
                <div style={{ display: "flex", gap: "20px" }}>
                  <div style={{ flex: 1 }}>
                    <label style={{ display: "block", marginBottom: "6px", fontSize: "0.875rem", color: "var(--text-secondary)" }}>SSH Host</label>
                    <input 
                      type="text" 
                      value={envHost} 
                      required
                      onChange={(e) => setEnvHost(e.target.value)} 
                      placeholder="e.g. 192.168.1.100, app.myserver.com"
                      style={{ width: "100%", padding: "10px", borderRadius: "6px", border: "1px solid var(--border-color)", backgroundColor: "var(--bg-primary)", color: "var(--text-primary)" }}
                    />
                  </div>
                  <div style={{ flex: 1 }}>
                    <label style={{ display: "block", marginBottom: "6px", fontSize: "0.875rem", color: "var(--text-secondary)" }}>SSH User</label>
                    <input 
                      type="text" 
                      value={envUser} 
                      required
                      onChange={(e) => setEnvUser(e.target.value)} 
                      placeholder="e.g. root, ubuntu"
                      style={{ width: "100%", padding: "10px", borderRadius: "6px", border: "1px solid var(--border-color)", backgroundColor: "var(--bg-primary)", color: "var(--text-primary)" }}
                    />
                  </div>
                </div>

                <div>
                  <label style={{ display: "block", marginBottom: "6px", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
                    SSH Private Key <span style={{ fontSize: "0.75rem", color: "var(--text-tertiary)" }}>{envSshKey === "********" ? "(Stored securely in Vault)" : "(Optional private key string)"}</span>
                  </label>
                  <textarea 
                    value={envSshKey} 
                    onChange={(e) => setEnvSshKey(e.target.value)} 
                    placeholder="-----BEGIN OPENSSH PRIVATE KEY-----&#10;...&#10;-----END OPENSSH PRIVATE KEY-----"
                    rows={4}
                    style={{ 
                      width: "100%", 
                      padding: "10px", 
                      borderRadius: "6px", 
                      border: "1px solid var(--border-color)", 
                      backgroundColor: "var(--bg-primary)", 
                      color: "var(--text-primary)", 
                      fontFamily: "monospace", 
                      fontSize: "0.85rem",
                      whiteSpace: "pre"
                    }}
                  />
                </div>
              </div>
            )}

            <div>
              <label style={{ display: "block", marginBottom: "6px", fontSize: "0.875rem", color: "var(--text-secondary)" }}>Extra Configuration (JSON)</label>
              <textarea 
                value={envExtraConfig} 
                onChange={(e) => setEnvExtraConfig(e.target.value)} 
                rows={2}
                style={{ width: "100%", padding: "10px", borderRadius: "6px", border: "1px solid var(--border-color)", backgroundColor: "var(--bg-primary)", color: "var(--text-primary)", fontFamily: "monospace", fontSize: "0.875rem" }}
              />
            </div>

            <div style={{ display: "flex", gap: "12px", marginTop: "10px" }}>
              <button type="submit" style={{ padding: "10px 20px", backgroundColor: "var(--accent-primary)", color: "#fff", border: "none", borderRadius: "8px", cursor: "pointer", fontWeight: 500 }}>
                {editingEnv ? "Save Changes" : "Create Environment"}
              </button>
              <button 
                type="button" 
                onClick={() => { setIsFormOpen(false); resetForm(); }} 
                style={{ padding: "10px 20px", backgroundColor: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border-color)", borderRadius: "8px", cursor: "pointer" }}
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      <div className="glass-panel" style={{ padding: "24px" }}>
        {environments.length === 0 ? (
          <p style={{ color: "var(--text-tertiary)" }}>No environments found.</p>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border-color)", color: "var(--text-secondary)" }}>
                <th style={{ padding: "12px 12px" }}>Name</th>
                <th style={{ padding: "12px 12px" }}>Type</th>
                <th style={{ padding: "12px 12px" }}>Path / Working Directory</th>
                <th style={{ padding: "12px 12px" }}>Configuration Details</th>
                <th style={{ padding: "12px 12px", width: "140px" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {environments.map((env) => (
                <tr key={env.id} style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                  <td style={{ padding: "16px 12px" }}>
                    <div style={{ fontWeight: 600, display: "flex", alignItems: "center", gap: "8px" }}>
                      {getEnvIcon(env.config?.type)}
                      {env.name}
                    </div>
                    <div style={{ fontSize: "0.75rem", color: "var(--text-tertiary)", marginTop: "4px" }}>{env.description}</div>
                  </td>
                  <td style={{ padding: "16px 12px" }}>
                    <span style={{ 
                      display: "inline-block", padding: "4px 8px", borderRadius: "12px", fontSize: "0.75rem",
                      backgroundColor: "var(--bg-glass-hover)", color: "var(--text-primary)"
                    }}>
                      {getTypeName(env.config?.type)}
                    </span>
                  </td>
                  <td style={{ padding: "16px 12px", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
                    {env.config?.path ? (
                      <span style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                        <Folder size={14} style={{ color: "var(--text-tertiary)" }} /> {env.config.path}
                      </span>
                    ) : (
                      <span style={{ color: "var(--text-tertiary)", fontStyle: "italic" }}>System default</span>
                    )}
                  </td>
                  <td style={{ padding: "16px 12px", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
                    {env.config?.type === EnvironmentType.DOCKER && <span>Image: <strong style={{ color: "var(--text-primary)" }}>{env.config.image || "N/A"}</strong></span>}
                    {env.config?.type === EnvironmentType.PYTHON && <span>Venv: <strong style={{ color: "var(--text-primary)" }}>{env.config.pythonPath || "N/A"}</strong></span>}
                    {env.config?.type === EnvironmentType.SSH && (
                      <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                        <span>Host: <strong style={{ color: "var(--text-primary)" }}>{env.config.host || "N/A"}</strong> (User: {env.config.user || "N/A"})</span>
                        {env.config.sshKey && <span style={{ fontSize: "0.75rem", color: "#34d399" }}>✓ SSH Key Loaded</span>}
                      </div>
                    )}
                    {env.config?.type === EnvironmentType.LOCAL && <span style={{ color: "var(--text-tertiary)" }}>Host operating system</span>}
                  </td>
                  <td style={{ padding: "16px 12px" }}>
                    <div style={{ display: "flex", gap: "12px" }}>
                      <button 
                        onClick={() => handleEditClick(env)}
                        style={{ 
                          background: "none", 
                          border: "none", 
                          color: "var(--accent-primary)", 
                          cursor: "pointer",
                          display: "flex",
                          alignItems: "center",
                          gap: "4px",
                          fontSize: "0.875rem"
                        }}
                        title="Edit Environment"
                      >
                        <Edit2 size={16} /> Edit
                      </button>
                      <button 
                        onClick={() => handleDelete(env.id)}
                        disabled={env.id === "default-local-env-id"}
                        style={{ 
                          background: "none", 
                          border: "none", 
                          color: env.id === "default-local-env-id" ? "var(--text-tertiary)" : "#ef4444", 
                          cursor: env.id === "default-local-env-id" ? "not-allowed" : "pointer",
                          display: "flex",
                          alignItems: "center",
                          gap: "4px",
                          fontSize: "0.875rem"
                        }}
                        title={env.id === "default-local-env-id" ? "Cannot delete default local environment" : "Delete Environment"}
                      >
                        <Trash2 size={16} /> Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
