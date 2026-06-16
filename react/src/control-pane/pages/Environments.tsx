import { useEffect, useState } from "react";
import { environmentClient } from "../grpcClient";
import { EnvironmentType } from "../../gen/environment_pb";

export default function EnvironmentsPage() {
  const [environments, setEnvironments] = useState<any[]>([]);
  const [isCreating, setIsCreating] = useState(false);
  const [newEnvName, setNewEnvName] = useState("");
  const [newEnvDescription, setNewEnvDescription] = useState("");
  const [newEnvType, setNewEnvType] = useState<EnvironmentType>(EnvironmentType.LOCAL);
  const [newEnvImage, setNewEnvImage] = useState("");
  const [newEnvHost, setNewEnvHost] = useState("");
  const [newEnvUser, setNewEnvUser] = useState("");
  const [newEnvExtraConfig, setNewEnvExtraConfig] = useState("{}");

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

  const handleCreate = async () => {
    try {
      await environmentClient.createEnvironment({
        name: newEnvName || "New Environment",
        description: newEnvDescription,
        config: {
          type: newEnvType,
          image: newEnvType === EnvironmentType.DOCKER ? newEnvImage : undefined,
          host: newEnvType === EnvironmentType.SSH ? newEnvHost : undefined,
          user: newEnvType === EnvironmentType.SSH ? newEnvUser : undefined,
          extraConfig: newEnvExtraConfig,
        }
      });
      setIsCreating(false);
      setNewEnvName("");
      setNewEnvDescription("");
      setNewEnvType(EnvironmentType.LOCAL);
      setNewEnvImage("");
      setNewEnvHost("");
      setNewEnvUser("");
      setNewEnvExtraConfig("{}");
      fetchEnvironments();
    } catch (e) {
      console.error("Failed to create environment", e);
      alert("Failed to create environment. Check console for details.");
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

  const getTypeName = (type: EnvironmentType) => {
    if (type === EnvironmentType.LOCAL) return "Local";
    if (type === EnvironmentType.DOCKER) return "Docker";
    if (type === EnvironmentType.SSH) return "SSH";
    return "Unknown";
  };

  return (
    <div className="animate-fade-in">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "32px" }}>
        <div>
          <h1 style={{ marginBottom: "8px" }}>Execution Environments</h1>
          <p style={{ color: "var(--text-secondary)", margin: 0 }}>Configure sandboxes and environments for process execution.</p>
        </div>
        <button 
          onClick={() => setIsCreating(true)}
          style={{
            padding: "8px 16px",
            backgroundColor: "var(--accent-primary)",
            color: "#fff",
            border: "none",
            borderRadius: "6px",
            cursor: "pointer",
            fontWeight: 500
          }}
        >
          New Environment
        </button>
      </div>

      {isCreating && (
        <div className="glass-panel" style={{ padding: "24px", marginBottom: "32px" }}>
          <h3 style={{ marginTop: 0, marginBottom: "16px" }}>Create New Environment</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
            <div>
              <label style={{ display: "block", marginBottom: "4px", fontSize: "0.875rem", color: "var(--text-secondary)" }}>Name</label>
              <input 
                type="text" 
                value={newEnvName} 
                onChange={(e) => setNewEnvName(e.target.value)} 
                placeholder="My Environment"
                style={{ width: "100%", padding: "8px", borderRadius: "4px", border: "1px solid var(--border-color)", backgroundColor: "var(--bg-tertiary)", color: "var(--text-primary)" }}
              />
            </div>
            <div>
              <label style={{ display: "block", marginBottom: "4px", fontSize: "0.875rem", color: "var(--text-secondary)" }}>Description</label>
              <input 
                type="text" 
                value={newEnvDescription} 
                onChange={(e) => setNewEnvDescription(e.target.value)} 
                placeholder="Description of the environment"
                style={{ width: "100%", padding: "8px", borderRadius: "4px", border: "1px solid var(--border-color)", backgroundColor: "var(--bg-tertiary)", color: "var(--text-primary)" }}
              />
            </div>
            <div>
              <label style={{ display: "block", marginBottom: "4px", fontSize: "0.875rem", color: "var(--text-secondary)" }}>Type</label>
              <select 
                value={newEnvType} 
                onChange={(e) => setNewEnvType(Number(e.target.value))}
                style={{ width: "100%", padding: "8px", borderRadius: "4px", border: "1px solid var(--border-color)", backgroundColor: "var(--bg-tertiary)", color: "var(--text-primary)" }}
              >
                <option value={EnvironmentType.LOCAL}>Local Machine</option>
                <option value={EnvironmentType.DOCKER}>Docker Container</option>
                <option value={EnvironmentType.SSH}>Remote SSH Host</option>
              </select>
            </div>
            
            {newEnvType === EnvironmentType.DOCKER && (
              <div>
                <label style={{ display: "block", marginBottom: "4px", fontSize: "0.875rem", color: "var(--text-secondary)" }}>Docker Image</label>
                <input 
                  type="text" 
                  value={newEnvImage} 
                  onChange={(e) => setNewEnvImage(e.target.value)} 
                  placeholder="e.g., ubuntu:latest"
                  style={{ width: "100%", padding: "8px", borderRadius: "4px", border: "1px solid var(--border-color)", backgroundColor: "var(--bg-tertiary)", color: "var(--text-primary)" }}
                />
              </div>
            )}

            {newEnvType === EnvironmentType.SSH && (
              <>
                <div>
                  <label style={{ display: "block", marginBottom: "4px", fontSize: "0.875rem", color: "var(--text-secondary)" }}>SSH Host</label>
                  <input 
                    type="text" 
                    value={newEnvHost} 
                    onChange={(e) => setNewEnvHost(e.target.value)} 
                    placeholder="e.g., 192.168.1.100"
                    style={{ width: "100%", padding: "8px", borderRadius: "4px", border: "1px solid var(--border-color)", backgroundColor: "var(--bg-tertiary)", color: "var(--text-primary)" }}
                  />
                </div>
                <div>
                  <label style={{ display: "block", marginBottom: "4px", fontSize: "0.875rem", color: "var(--text-secondary)" }}>SSH User</label>
                  <input 
                    type="text" 
                    value={newEnvUser} 
                    onChange={(e) => setNewEnvUser(e.target.value)} 
                    placeholder="e.g., root"
                    style={{ width: "100%", padding: "8px", borderRadius: "4px", border: "1px solid var(--border-color)", backgroundColor: "var(--bg-tertiary)", color: "var(--text-primary)" }}
                  />
                </div>
              </>
            )}

            <div style={{ display: "flex", gap: "12px", marginTop: "8px" }}>
              <button onClick={handleCreate} style={{ padding: "8px 16px", backgroundColor: "var(--accent-primary)", color: "#fff", border: "none", borderRadius: "6px", cursor: "pointer" }}>Save Environment</button>
              <button onClick={() => setIsCreating(false)} style={{ padding: "8px 16px", backgroundColor: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border-color)", borderRadius: "6px", cursor: "pointer" }}>Cancel</button>
            </div>
          </div>
        </div>
      )}

      <div className="glass-panel" style={{ padding: "24px" }}>
        {environments.length === 0 ? (
          <p style={{ color: "var(--text-tertiary)" }}>No environments found.</p>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border-color)", color: "var(--text-secondary)" }}>
                <th style={{ padding: "12px 8px" }}>Name</th>
                <th style={{ padding: "12px 8px" }}>Type</th>
                <th style={{ padding: "12px 8px" }}>Configuration</th>
                <th style={{ padding: "12px 8px", width: "80px" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {environments.map((env) => (
                <tr key={env.id} style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                  <td style={{ padding: "12px 8px" }}>
                    <div style={{ fontWeight: 500 }}>{env.name}</div>
                    <div style={{ fontSize: "0.75rem", color: "var(--text-tertiary)" }}>{env.description}</div>
                  </td>
                  <td style={{ padding: "12px 8px" }}>
                    <span style={{ 
                      display: "inline-block", padding: "4px 8px", borderRadius: "12px", fontSize: "0.75rem",
                      backgroundColor: "rgba(255,255,255,0.1)", color: "var(--text-secondary)"
                    }}>
                      {getTypeName(env.config?.type)}
                    </span>
                  </td>
                  <td style={{ padding: "12px 8px", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
                    {env.config?.type === EnvironmentType.DOCKER && <span>Image: {env.config.image || "N/A"}</span>}
                    {env.config?.type === EnvironmentType.SSH && <span>Host: {env.config.host || "N/A"} (User: {env.config.user || "N/A"})</span>}
                    {env.config?.type === EnvironmentType.LOCAL && <span>Local system context</span>}
                  </td>
                  <td style={{ padding: "12px 8px" }}>
                    <button 
                      onClick={() => handleDelete(env.id)}
                      disabled={env.id === "default-local-env-id"}
                      style={{ 
                        background: "none", 
                        border: "none", 
                        color: env.id === "default-local-env-id" ? "var(--text-tertiary)" : "#ef4444", 
                        cursor: env.id === "default-local-env-id" ? "not-allowed" : "pointer",
                        textDecoration: env.id === "default-local-env-id" ? "none" : "underline"
                      }}
                      title={env.id === "default-local-env-id" ? "Cannot delete default local environment" : "Delete"}
                    >
                      Delete
                    </button>
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
