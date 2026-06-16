import { useEffect, useState } from "react";
import { processClient, environmentClient } from "../grpcClient";
import { invoke } from "@tauri-apps/api/core";

export default function ProcessesPage() {
  const [processes, setProcesses] = useState<any[]>([]);
  const [environments, setEnvironments] = useState<any[]>([]);
  const [isCreating, setIsCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [newCommand, setNewCommand] = useState("");
  const [newArgs, setNewArgs] = useState("");
  const [newEnvId, setNewEnvId] = useState("");

  const [viewingLogsFor, setViewingLogsFor] = useState<string | null>(null);
  const [logsContent, setLogsContent] = useState<string>("");

  const fetchData = async () => {
    try {
      const pRes = await processClient.listProcesses({});
      setProcesses(pRes.processes);
      
      const eRes = await environmentClient.listEnvironments({});
      setEnvironments(eRes.environments);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 2000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    let logInterval: any;
    if (viewingLogsFor) {
      const fetchLogs = async () => {
        try {
          const logs = await invoke("read_process_logs", { id: viewingLogsFor });
          setLogsContent(logs as string);
        } catch (e) {
          setLogsContent("Failed to load logs...");
        }
      };
      fetchLogs();
      logInterval = setInterval(fetchLogs, 1000);
    }
    return () => clearInterval(logInterval);
  }, [viewingLogsFor]);

  const handleCreate = async () => {
    try {
      await processClient.createProcess({
        name: newName || "New Process",
        description: newDesc,
        config: {
          command: newCommand || "echo",
          args: newArgs ? newArgs.split(" ") : [],
          envVars: "{}",
          cwd: "/",
          environmentId: newEnvId || undefined,
          autostart: false,
        }
      });
      setIsCreating(false);
      setNewName("");
      setNewDesc("");
      setNewCommand("");
      setNewArgs("");
      setNewEnvId("");
      fetchData();
    } catch (e) {
      console.error(e);
      alert("Failed to create process");
    }
  };

  const handleStart = async (id: string) => {
    try {
      await processClient.startProcess({ id });
      fetchData();
    } catch (e) {
      console.error(e);
      alert("Failed to start process");
    }
  };

  const handleStop = async (id: string) => {
    try {
      await processClient.stopProcess({ id });
      fetchData();
    } catch (e) {
      console.error(e);
      alert("Failed to stop process");
    }
  };

  const handleDelete = async (id: string) => {
    if (confirm("Delete this process?")) {
      try {
        await processClient.deleteProcess({ id });
        fetchData();
      } catch (e) {
        console.error(e);
      }
    }
  };

  const getEnvName = (id?: string) => {
    if (!id) return "Default (Local)";
    const env = environments.find(e => e.id === id);
    return env ? env.name : id;
  };

  return (
    <div className="animate-fade-in">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "32px" }}>
        <div>
          <h1 style={{ marginBottom: "8px" }}>Process Manager</h1>
          <p style={{ color: "var(--text-secondary)", margin: 0 }}>Monitor background tasks and worker processes.</p>
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
          New Process
        </button>
      </div>

      {isCreating && (
        <div className="glass-panel" style={{ padding: "24px", marginBottom: "32px" }}>
          <h3 style={{ marginTop: 0, marginBottom: "16px" }}>Create New Process</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
            <div style={{ display: "flex", gap: "16px" }}>
              <div style={{ flex: 1 }}>
                <label style={{ display: "block", marginBottom: "4px", fontSize: "0.875rem", color: "var(--text-secondary)" }}>Name</label>
                <input type="text" value={newName} onChange={(e) => setNewName(e.target.value)} style={{ width: "100%", padding: "8px", borderRadius: "4px", border: "1px solid var(--border-color)", backgroundColor: "var(--bg-tertiary)", color: "var(--text-primary)" }} />
              </div>
              <div style={{ flex: 1 }}>
                <label style={{ display: "block", marginBottom: "4px", fontSize: "0.875rem", color: "var(--text-secondary)" }}>Environment</label>
                <select value={newEnvId} onChange={(e) => setNewEnvId(e.target.value)} style={{ width: "100%", padding: "8px", borderRadius: "4px", border: "1px solid var(--border-color)", backgroundColor: "var(--bg-tertiary)", color: "var(--text-primary)" }}>
                  <option value="">Default (Local)</option>
                  {environments.map(e => (
                    <option key={e.id} value={e.id}>{e.name} ({e.config?.type === 1 ? "Docker" : e.config?.type === 2 ? "SSH" : "Local"})</option>
                  ))}
                </select>
              </div>
            </div>
            
            <div style={{ display: "flex", gap: "16px" }}>
              <div style={{ flex: 1 }}>
                <label style={{ display: "block", marginBottom: "4px", fontSize: "0.875rem", color: "var(--text-secondary)" }}>Command</label>
                <input type="text" value={newCommand} onChange={(e) => setNewCommand(e.target.value)} placeholder="e.g., node, python, echo" style={{ width: "100%", padding: "8px", borderRadius: "4px", border: "1px solid var(--border-color)", backgroundColor: "var(--bg-tertiary)", color: "var(--text-primary)" }} />
              </div>
              <div style={{ flex: 1 }}>
                <label style={{ display: "block", marginBottom: "4px", fontSize: "0.875rem", color: "var(--text-secondary)" }}>Arguments (space separated)</label>
                <input type="text" value={newArgs} onChange={(e) => setNewArgs(e.target.value)} placeholder="e.g., script.py --verbose" style={{ width: "100%", padding: "8px", borderRadius: "4px", border: "1px solid var(--border-color)", backgroundColor: "var(--bg-tertiary)", color: "var(--text-primary)" }} />
              </div>
            </div>

            <div style={{ display: "flex", gap: "12px", marginTop: "8px" }}>
              <button onClick={handleCreate} style={{ padding: "8px 16px", backgroundColor: "var(--accent-primary)", color: "#fff", border: "none", borderRadius: "6px", cursor: "pointer" }}>Save Process</button>
              <button onClick={() => setIsCreating(false)} style={{ padding: "8px 16px", backgroundColor: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border-color)", borderRadius: "6px", cursor: "pointer" }}>Cancel</button>
            </div>
          </div>
        </div>
      )}

      {viewingLogsFor && (
        <div style={{
          position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
          backgroundColor: "rgba(0,0,0,0.5)", zIndex: 9999,
          display: "flex", alignItems: "center", justifyContent: "center", padding: "32px"
        }}>
          <div className="glass-panel" style={{ width: "100%", maxWidth: "800px", height: "80vh", display: "flex", flexDirection: "column", padding: "24px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "16px" }}>
              <h3 style={{ margin: 0 }}>Process Logs</h3>
              <button onClick={() => setViewingLogsFor(null)} style={{ background: "none", border: "none", color: "var(--text-secondary)", cursor: "pointer", fontSize: "1.25rem" }}>×</button>
            </div>
            <pre style={{ 
              flex: 1, overflowY: "auto", margin: 0, padding: "16px",
              backgroundColor: "rgba(0,0,0,0.3)", borderRadius: "8px",
              fontFamily: "monospace", fontSize: "0.875rem", whiteSpace: "pre-wrap", wordBreak: "break-all"
            }}>
              {logsContent || "Waiting for logs..."}
            </pre>
          </div>
        </div>
      )}

      <div className="glass-panel" style={{ padding: "24px" }}>
        {processes.length === 0 ? (
          <p style={{ color: "var(--text-tertiary)" }}>No active processes.</p>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border-color)", color: "var(--text-secondary)" }}>
                <th style={{ padding: "12px 8px" }}>Name / Env</th>
                <th style={{ padding: "12px 8px" }}>Command</th>
                <th style={{ padding: "12px 8px" }}>Status</th>
                <th style={{ padding: "12px 8px", width: "240px" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {processes.map((p) => (
                <tr key={p.id} style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                  <td style={{ padding: "12px 8px" }}>
                    <div style={{ fontWeight: 500 }}>{p.name} {p.config?.autostart && <span style={{ fontSize: "0.6rem", color: "var(--accent-primary)", border: "1px solid var(--accent-primary)", padding: "2px 4px", borderRadius: "4px", marginLeft: "4px" }}>AUTO</span>}</div>
                    <div style={{ fontSize: "0.75rem", color: "var(--text-tertiary)" }}>Env: {getEnvName(p.config?.environmentId)}</div>
                  </td>
                  <td style={{ padding: "12px 8px" }}>
                    <div style={{ fontFamily: "monospace", fontSize: "0.875rem" }}>
                      {p.config?.command} {p.config?.args?.join(" ")}
                    </div>
                  </td>
                  <td style={{ padding: "12px 8px" }}>
                    <span style={{ 
                      display: "inline-block", padding: "4px 8px", borderRadius: "12px", fontSize: "0.75rem",
                      backgroundColor: p.status === "running" ? "rgba(16, 185, 129, 0.2)" : "rgba(239, 68, 68, 0.2)",
                      color: p.status === "running" ? "#10b981" : "#ef4444"
                    }}>
                      {p.status.toUpperCase()}
                    </span>
                  </td>
                  <td style={{ padding: "12px 8px" }}>
                    <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                      {p.status === "stopped" ? (
                        <button onClick={() => handleStart(p.id)} style={{ padding: "4px 8px", backgroundColor: "var(--accent-primary)", color: "#fff", border: "none", borderRadius: "4px", cursor: "pointer", fontSize: "0.75rem" }}>Start</button>
                      ) : (
                        <button onClick={() => handleStop(p.id)} style={{ padding: "4px 8px", backgroundColor: "var(--bg-tertiary)", color: "var(--text-primary)", border: "1px solid var(--border-color)", borderRadius: "4px", cursor: "pointer", fontSize: "0.75rem" }}>Stop</button>
                      )}
                      <button onClick={() => setViewingLogsFor(p.id)} style={{ padding: "4px 8px", backgroundColor: "rgba(255,255,255,0.1)", color: "var(--text-primary)", border: "none", borderRadius: "4px", cursor: "pointer", fontSize: "0.75rem" }}>Logs</button>
                      <button onClick={() => handleDelete(p.id)} style={{ padding: "4px 8px", backgroundColor: "transparent", color: "#ef4444", border: "none", cursor: "pointer", fontSize: "0.75rem", textDecoration: "underline" }}>Delete</button>
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
