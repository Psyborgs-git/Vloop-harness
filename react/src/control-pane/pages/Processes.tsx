import { useEffect, useState } from "react";
import { processClient, environmentClient } from "../grpcClient";
import { invoke } from "@tauri-apps/api/core";
import { Play, Square, Trash2, Edit2, Terminal, Plus, CheckSquare, Square as SquareIcon, X } from "lucide-react";

export default function ProcessesPage() {
  const [processes, setProcesses] = useState<any[]>([]);
  const [environments, setEnvironments] = useState<any[]>([]);
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [editingProcess, setEditingProcess] = useState<any | null>(null);

  // Form states
  const [nameInput, setNameInput] = useState("");
  const [descInput, setDescInput] = useState("");
  const [commandInput, setCommandInput] = useState("");
  const [argsInput, setArgsInput] = useState("");
  const [envIdInput, setEnvIdInput] = useState("");
  const [cwdInput, setCwdInput] = useState("");
  const [autostartInput, setAutostartInput] = useState(false);
  const [envVarsInput, setEnvVarsInput] = useState("{}");

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

  const resetForm = () => {
    setNameInput("");
    setDescInput("");
    setCommandInput("");
    setArgsInput("");
    setEnvIdInput("");
    setCwdInput("");
    setAutostartInput(false);
    setEnvVarsInput("{}");
    setEditingProcess(null);
  };

  const handleEditClick = (p: any) => {
    setEditingProcess(p);
    setNameInput(p.name);
    setDescInput(p.description);
    setCommandInput(p.config?.command ?? "");
    setArgsInput(p.config?.args?.join(" ") ?? "");
    setEnvIdInput(p.config?.environmentId ?? "");
    setCwdInput(p.config?.cwd ?? "/");
    setAutostartInput(p.config?.autostart ?? false);
    setEnvVarsInput(p.config?.envVars ?? "{}");
    setIsFormOpen(true);
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const payload = {
        name: nameInput || "Unnamed Process",
        description: descInput,
        config: {
          command: commandInput || "echo",
          args: argsInput ? argsInput.split(" ") : [],
          envVars: envVarsInput || "{}",
          cwd: cwdInput || "/",
          environmentId: envIdInput || undefined,
          autostart: autostartInput,
        }
      };

      if (editingProcess) {
        await processClient.updateProcess({
          id: editingProcess.id,
          ...payload
        });
      } else {
        await processClient.createProcess(payload);
      }

      setIsFormOpen(false);
      resetForm();
      fetchData();
    } catch (e) {
      console.error(e);
      alert("Failed to save process configuration. Check console for details.");
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
    if (confirm("Are you sure you want to delete this process?")) {
      try {
        await processClient.deleteProcess({ id });
        fetchData();
      } catch (e) {
        console.error(e);
        alert("Failed to delete process");
      }
    }
  };

  const getEnvName = (id?: string) => {
    if (!id) return "Default (Local)";
    const env = environments.find(e => e.id === id);
    if (!env) return id || "Default (Local)";

    let typeName = "Local";
    if (env.config?.type === 1) typeName = "Docker";
    else if (env.config?.type === 2) typeName = "SSH";
    else if (env.config?.type === 3) typeName = "Python";

    return `${env.name} (${typeName})`;
  };

  return (
    <div className="animate-fade-in">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "32px" }}>
        <div>
          <h1 style={{ marginBottom: "8px" }}>Process Manager</h1>
          <p style={{ color: "var(--text-secondary)", margin: 0 }}>Configure, run, and monitor background tasks and workers.</p>
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
          <Plus size={18} /> New Process
        </button>
      </div>

      {isFormOpen && (
        <div className="glass-panel" style={{ padding: "28px", marginBottom: "32px", borderRadius: "16px" }}>
          <h3 style={{ marginTop: 0, marginBottom: "20px", fontSize: "1.2rem", fontWeight: 600 }}>
            {editingProcess ? `Edit Process: ${editingProcess.name}` : "Create New Process"}
          </h3>
          <form onSubmit={handleSave} style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
            <div style={{ display: "flex", gap: "20px" }}>
              <div style={{ flex: 1 }}>
                <label style={{ display: "block", marginBottom: "6px", fontSize: "0.875rem", color: "var(--text-secondary)" }}>Name</label>
                <input
                  type="text"
                  value={nameInput}
                  required
                  onChange={(e) => setNameInput(e.target.value)}
                  placeholder="e.g. Scrapy Worker, API Server"
                  style={{ width: "100%", padding: "10px", borderRadius: "6px", border: "1px solid var(--border-color)", backgroundColor: "var(--bg-primary)", color: "var(--text-primary)" }}
                />
              </div>
              <div style={{ flex: 1 }}>
                <label style={{ display: "block", marginBottom: "6px", fontSize: "0.875rem", color: "var(--text-secondary)" }}>Execution Environment</label>
                <select
                  value={envIdInput}
                  onChange={(e) => setEnvIdInput(e.target.value)}
                  style={{ width: "100%", padding: "10px", borderRadius: "6px", border: "1px solid var(--border-color)", backgroundColor: "var(--bg-primary)", color: "var(--text-primary)" }}
                >
                  <option value="">Default (Local)</option>
                  {environments.map(e => {
                    let typeName = "Local";
                    if (e.config?.type === 1) typeName = "Docker";
                    else if (e.config?.type === 2) typeName = "SSH";
                    else if (e.config?.type === 3) typeName = "Python";
                    return (
                      <option key={e.id} value={e.id}>{e.name} ({typeName})</option>
                    );
                  })}
                </select>
              </div>
            </div>

            <div>
              <label style={{ display: "block", marginBottom: "6px", fontSize: "0.875rem", color: "var(--text-secondary)" }}>Description</label>
              <input
                type="text"
                value={descInput}
                onChange={(e) => setDescInput(e.target.value)}
                placeholder="What does this process do?"
                style={{ width: "100%", padding: "10px", borderRadius: "6px", border: "1px solid var(--border-color)", backgroundColor: "var(--bg-primary)", color: "var(--text-primary)" }}
              />
            </div>

            <div style={{ display: "flex", gap: "20px" }}>
              <div style={{ flex: 1 }}>
                <label style={{ display: "block", marginBottom: "6px", fontSize: "0.875rem", color: "var(--text-secondary)" }}>Executable/Command</label>
                <input
                  type="text"
                  value={commandInput}
                  required
                  onChange={(e) => setCommandInput(e.target.value)}
                  placeholder="e.g. python, npm, ./script.sh"
                  style={{ width: "100%", padding: "10px", borderRadius: "6px", border: "1px solid var(--border-color)", backgroundColor: "var(--bg-primary)", color: "var(--text-primary)" }}
                />
              </div>
              <div style={{ flex: 1 }}>
                <label style={{ display: "block", marginBottom: "6px", fontSize: "0.875rem", color: "var(--text-secondary)" }}>Arguments (space separated)</label>
                <input
                  type="text"
                  value={argsInput}
                  onChange={(e) => setArgsInput(e.target.value)}
                  placeholder="e.g. run dev, -m my_module"
                  style={{ width: "100%", padding: "10px", borderRadius: "6px", border: "1px solid var(--border-color)", backgroundColor: "var(--bg-primary)", color: "var(--text-primary)" }}
                />
              </div>
            </div>

            <div style={{ display: "flex", gap: "20px" }}>
              <div style={{ flex: 1 }}>
                <label style={{ display: "block", marginBottom: "6px", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
                  Working Directory <span style={{ fontSize: "0.75rem", color: "var(--text-tertiary)" }}>(Fallback if environment path empty)</span>
                </label>
                <input
                  type="text"
                  value={cwdInput}
                  onChange={(e) => setCwdInput(e.target.value)}
                  placeholder="e.g. /var/www/my-project"
                  style={{ width: "100%", padding: "10px", borderRadius: "6px", border: "1px solid var(--border-color)", backgroundColor: "var(--bg-primary)", color: "var(--text-primary)" }}
                />
              </div>
              <div style={{ flex: 1, display: "flex", alignItems: "flex-end", paddingBottom: "10px" }}>
                <button
                  type="button"
                  onClick={() => setAutostartInput(!autostartInput)}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                    background: "none",
                    border: "none",
                    color: "var(--text-primary)",
                    cursor: "pointer",
                    fontWeight: 500,
                    fontSize: "0.95rem"
                  }}
                >
                  {autostartInput ? <CheckSquare size={20} style={{ color: "var(--accent-primary)" }} /> : <SquareIcon size={20} />}
                  Auto-start process on boot
                </button>
              </div>
            </div>

            <div>
              <label style={{ display: "block", marginBottom: "6px", fontSize: "0.875rem", color: "var(--text-secondary)" }}>Environment Variables (JSON String)</label>
              <textarea
                value={envVarsInput}
                onChange={(e) => setEnvVarsInput(e.target.value)}
                rows={2}
                placeholder='{"PORT": "8080", "NODE_ENV": "production"}'
                style={{ width: "100%", padding: "10px", borderRadius: "6px", border: "1px solid var(--border-color)", backgroundColor: "var(--bg-primary)", color: "var(--text-primary)", fontFamily: "monospace", fontSize: "0.875rem" }}
              />
            </div>

            <div style={{ display: "flex", gap: "12px", marginTop: "10px" }}>
              <button type="submit" style={{ padding: "10px 20px", backgroundColor: "var(--accent-primary)", color: "#fff", border: "none", borderRadius: "8px", cursor: "pointer", fontWeight: 500 }}>
                {editingProcess ? "Save Changes" : "Create Process"}
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

      {viewingLogsFor && (
        <div style={{
          position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
          backgroundColor: "rgba(0,0,0,0.7)", zIndex: 9999,
          display: "flex", alignItems: "center", justifyContent: "center", padding: "32px",
          backdropFilter: "blur(4px)"
        }}>
          <div className="glass-panel" style={{ width: "100%", maxWidth: "900px", height: "85vh", display: "flex", flexDirection: "column", padding: "28px", borderRadius: "16px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
              <h3 style={{ margin: 0, fontSize: "1.25rem", fontWeight: 600 }}>Process Logs</h3>
              <button onClick={() => setViewingLogsFor(null)} style={{ background: "none", border: "none", color: "var(--text-secondary)", cursor: "pointer" }}>
                <X size={24} />
              </button>
            </div>
            <pre style={{
              flex: 1, overflowY: "auto", margin: 0, padding: "20px",
              backgroundColor: "rgba(0,0,0,0.5)", borderRadius: "10px", border: "1px solid var(--border-color)",
              fontFamily: "monospace", fontSize: "0.875rem", whiteSpace: "pre-wrap", wordBreak: "break-all",
              color: "#34d399"
            }}>
              {logsContent || "Waiting for logs..."}
            </pre>
          </div>
        </div>
      )}

      <div className="glass-panel" style={{ padding: "24px" }}>
        {processes.length === 0 ? (
          <p style={{ color: "var(--text-tertiary)" }}>No processes configured.</p>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border-color)", color: "var(--text-secondary)" }}>
                <th style={{ padding: "12px 12px" }}>Process / Environment</th>
                <th style={{ padding: "12px 12px" }}>Execution Command</th>
                <th style={{ padding: "12px 12px" }}>Status</th>
                <th style={{ padding: "12px 12px", width: "320px" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {processes.map((p) => (
                <tr key={p.id} style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                  <td style={{ padding: "18px 12px" }}>
                    <div style={{ fontWeight: 600, display: "flex", alignItems: "center", gap: "6px" }}>
                      {p.name}
                      {p.config?.autostart && (
                        <span style={{ fontSize: "0.6rem", color: "var(--accent-primary)", border: "1px solid var(--accent-primary)", padding: "2px 6px", borderRadius: "12px", marginLeft: "6px", fontWeight: 700 }}>AUTO</span>
                      )}
                    </div>
                    <div style={{ fontSize: "0.75rem", color: "var(--text-tertiary)", marginTop: "4px" }}>Env: {getEnvName(p.config?.environmentId)}</div>
                  </td>
                  <td style={{ padding: "18px 12px" }}>
                    <div style={{ fontFamily: "monospace", fontSize: "0.85rem", color: "var(--text-secondary)" }}>
                      {p.config?.command} {p.config?.args?.join(" ")}
                    </div>
                    {p.config?.cwd && p.config?.cwd !== "/" && (
                      <div style={{ fontSize: "0.7rem", color: "var(--text-tertiary)", marginTop: "4px" }}>Dir: {p.config.cwd}</div>
                    )}
                  </td>
                  <td style={{ padding: "18px 12px" }}>
                    <span style={{
                      display: "inline-block", padding: "4px 10px", borderRadius: "12px", fontSize: "0.7rem", fontWeight: 600,
                      backgroundColor: p.status === "running" ? "rgba(16, 185, 129, 0.15)" : "rgba(239, 68, 68, 0.15)",
                      color: p.status === "running" ? "#34d399" : "#f87171"
                    }}>
                      {p.status.toUpperCase()}
                    </span>
                  </td>
                  <td style={{ padding: "18px 12px" }}>
                    <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
                      {p.status === "stopped" ? (
                        <button
                          onClick={() => handleStart(p.id)}
                          style={{
                            padding: "6px 12px",
                            backgroundColor: "var(--accent-primary)",
                            color: "#fff",
                            border: "none",
                            borderRadius: "6px",
                            cursor: "pointer",
                            fontSize: "0.75rem",
                            display: "flex",
                            alignItems: "center",
                            gap: "4px",
                            fontWeight: 500
                          }}
                        >
                          <Play size={12} />
                        </button>
                      ) : (
                        <button
                          onClick={() => handleStop(p.id)}
                          style={{
                            padding: "6px 12px",
                            backgroundColor: "rgba(255, 255, 255, 0.1)",
                            color: "var(--text-primary)",
                            border: "1px solid var(--border-color)",
                            borderRadius: "6px",
                            cursor: "pointer",
                            fontSize: "0.75rem",
                            display: "flex",
                            alignItems: "center",
                            gap: "4px",
                            fontWeight: 500
                          }}
                        >
                          <Square size={12} />
                        </button>
                      )}

                      <button
                        onClick={() => setViewingLogsFor(p.id)}
                        style={{
                          padding: "6px 12px",
                          backgroundColor: "var(--bg-glass-hover)",
                          color: "var(--text-primary)",
                          border: "1px solid var(--border-color)",
                          borderRadius: "6px",
                          cursor: "pointer",
                          fontSize: "0.75rem",
                          display: "flex",
                          alignItems: "center",
                          gap: "4px"
                        }}
                      >
                        <Terminal size={12} /> Logs
                      </button>

                      <button
                        onClick={() => handleEditClick(p)}
                        style={{
                          background: "none",
                          border: "none",
                          color: "var(--text-secondary)",
                          cursor: "pointer",
                          fontSize: "0.75rem",
                          display: "flex",
                          alignItems: "center",
                          gap: "4px",
                          textDecoration: "underline"
                        }}
                      >
                        <Edit2 size={12} />
                      </button>

                      <button
                        onClick={() => handleDelete(p.id)}
                        style={{
                          background: "none",
                          border: "none",
                          color: "#f87171",
                          cursor: "pointer",
                          fontSize: "0.75rem",
                          display: "flex",
                          alignItems: "center",
                          gap: "4px",
                          textDecoration: "underline"
                        }}
                      >
                        <Trash2 size={12} />
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
