import { useEffect, useState } from "react";
import { systemClient } from "../grpcClient";

export default function DashboardPage() {
  const [health, setHealth] = useState<any>(null);

  const fetchHealth = async () => {
    try {
      const res = await systemClient.getHealth({});
      setHealth(res);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchHealth();
    const interval = setInterval(fetchHealth, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="animate-fade-in">
      <h1 style={{ marginBottom: "24px" }}>System Dashboard</h1>
      
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(250px, 1fr))", gap: "24px" }}>
        
        <div className="glass-panel" style={{ padding: "24px" }}>
          <h3 style={{ color: "var(--text-secondary)", marginBottom: "16px", fontSize: "0.875rem", textTransform: "uppercase", letterSpacing: "0.05em" }}>Python Kernel</h3>
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <div style={{ 
              width: "12px", height: "12px", borderRadius: "50%", 
              backgroundColor: health?.pythonOk ? "#10b981" : "#ef4444",
              boxShadow: health?.pythonOk ? "0 0 10px #10b981" : "0 0 10px #ef4444"
            }} />
            <span style={{ fontSize: "1.5rem", fontWeight: 600 }}>{health?.pythonOk ? "Online" : "Offline"}</span>
          </div>
        </div>

        <div className="glass-panel" style={{ padding: "24px" }}>
          <h3 style={{ color: "var(--text-secondary)", marginBottom: "16px", fontSize: "0.875rem", textTransform: "uppercase", letterSpacing: "0.05em" }}>Node Engine</h3>
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <div style={{ 
              width: "12px", height: "12px", borderRadius: "50%", 
              backgroundColor: health?.nodeOk ? "#10b981" : "#ef4444",
              boxShadow: health?.nodeOk ? "0 0 10px #10b981" : "0 0 10px #ef4444"
            }} />
            <span style={{ fontSize: "1.5rem", fontWeight: 600 }}>{health?.nodeOk ? "Online" : "Offline"}</span>
          </div>
        </div>

        <div className="glass-panel" style={{ padding: "24px" }}>
          <h3 style={{ color: "var(--text-secondary)", marginBottom: "16px", fontSize: "0.875rem", textTransform: "uppercase", letterSpacing: "0.05em" }}>Database</h3>
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <div style={{ 
              width: "12px", height: "12px", borderRadius: "50%", 
              backgroundColor: health?.dbAccessible ? "#10b981" : "#ef4444",
              boxShadow: health?.dbAccessible ? "0 0 10px #10b981" : "0 0 10px #ef4444"
            }} />
            <span style={{ fontSize: "1.5rem", fontWeight: 600 }}>{health?.dbAccessible ? "Connected" : "Error"}</span>
          </div>
        </div>

      </div>

      {health?.details && (
        <div className="glass-panel" style={{ marginTop: "24px", padding: "24px" }}>
          <h3 style={{ marginBottom: "16px" }}>Diagnostics</h3>
          <pre style={{ 
            color: "var(--text-secondary)", 
            fontSize: "0.875rem", 
            whiteSpace: "pre-wrap", 
            backgroundColor: "var(--bg-primary)", 
            padding: "16px", 
            borderRadius: "8px" 
          }}>{health.details}</pre>
        </div>
      )}
    </div>
  );
}
