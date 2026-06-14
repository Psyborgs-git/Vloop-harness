import { useEffect, useState } from "react";
import { processClient } from "../grpcClient";

export default function ProcessesPage() {
  const [processes, setProcesses] = useState<any[]>([]);

  const fetchProcesses = async () => {
    try {
      const res = await processClient.listProcesses({});
      setProcesses(res.processes);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchProcesses();
    const interval = setInterval(fetchProcesses, 2000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="animate-fade-in">
      <h1 style={{ marginBottom: "8px" }}>Process Manager</h1>
      <p style={{ color: "var(--text-secondary)", marginBottom: "32px" }}>Monitor background tasks and worker processes.</p>

      <div className="glass-panel" style={{ padding: "24px" }}>
        {processes.length === 0 ? (
          <p style={{ color: "var(--text-tertiary)" }}>No active processes.</p>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border-color)", color: "var(--text-secondary)" }}>
                <th style={{ padding: "12px 8px" }}>PID</th>
                <th style={{ padding: "12px 8px" }}>Command</th>
                <th style={{ padding: "12px 8px" }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {processes.map((p) => (
                <tr key={p.pid} style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                  <td style={{ padding: "12px 8px", fontFamily: "monospace" }}>{p.pid}</td>
                  <td style={{ padding: "12px 8px" }}>{p.command} {p.args.join(" ")}</td>
                  <td style={{ padding: "12px 8px" }}>
                    <span style={{ 
                      display: "inline-block", padding: "4px 8px", borderRadius: "12px", fontSize: "0.75rem",
                      backgroundColor: p.status === "running" ? "rgba(16, 185, 129, 0.2)" : "rgba(239, 68, 68, 0.2)",
                      color: p.status === "running" ? "#10b981" : "#ef4444"
                    }}>
                      {p.status.toUpperCase()}
                    </span>
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
