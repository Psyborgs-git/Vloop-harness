import { useEffect, useState, lazy, Suspense } from "react";
import { Routes, Route, Link, useLocation } from "react-router-dom";
import { Activity, KeyRound, Terminal, Server } from "lucide-react";
import { initGrpcClient } from "./grpcClient";

const DashboardPage = lazy(() => import("./pages/Dashboard"));
const VaultPage = lazy(() => import("./pages/Vault"));
const ProcessesPage = lazy(() => import("./pages/Processes"));
const TerminalPage = lazy(() => import("./pages/Terminal"));

function Sidebar() {
  const location = useLocation();

  const links = [
    { to: "/", icon: <Activity size={20} />, label: "Dashboard" },
    { to: "/vault", icon: <KeyRound size={20} />, label: "Vault" },
    { to: "/processes", icon: <Server size={20} />, label: "Processes" },
    { to: "/terminal", icon: <Terminal size={20} />, label: "Terminal" },
  ];

  return (
    <div style={{
      width: "240px",
      backgroundColor: "var(--bg-tertiary)",
      borderRight: "1px solid var(--border-color)",
      display: "flex",
      flexDirection: "column",
      padding: "20px 0",
      height: "100vh"
    }}>
      <div style={{ padding: "0 24px", marginBottom: "32px" }}>
        <h2 className="gradient-text" style={{ margin: 0, fontSize: "1.25rem" }}>Command Center</h2>
      </div>
      <nav style={{ display: "flex", flexDirection: "column", gap: "8px", padding: "0 12px" }}>
        {links.map((link) => {
          const isActive = location.pathname === link.to;
          return (
            <Link
              key={link.to}
              to={link.to}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "12px",
                padding: "10px 16px",
                borderRadius: "8px",
                color: isActive ? "var(--text-primary)" : "var(--text-secondary)",
                backgroundColor: isActive ? "var(--bg-glass-hover)" : "transparent",
                fontWeight: isActive ? 600 : 400,
                transition: "all 0.2s"
              }}
            >
              <div style={{ color: isActive ? "var(--accent-primary)" : "inherit" }}>
                {link.icon}
              </div>
              {link.label}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}

export default function App() {
  const [initialized, setInitialized] = useState(false);

  useEffect(() => {
    initGrpcClient().then(() => {
      setInitialized(true);
    });
  }, []);

  if (!initialized) {
    return (
      <div style={{ height: "100vh", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <p style={{ color: "var(--text-secondary)" }}>Initializing Connection...</p>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden" }}>
      <Sidebar />
      <main style={{ flex: 1, overflowY: "auto", padding: "32px" }}>
        <Suspense fallback={<p style={{ color: "var(--text-secondary)" }}>Loading Page...</p>}>
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/vault" element={<VaultPage />} />
            <Route path="/processes" element={<ProcessesPage />} />
            <Route path="/terminal" element={<TerminalPage />} />
          </Routes>
        </Suspense>
      </main>
    </div>
  );
}
