import { useEffect, useState, lazy, Suspense } from "react";
import { Routes, Route, Link, useLocation } from "react-router-dom";
import { Activity, KeyRound, Terminal, Server, Globe, ChevronLeft, ChevronRight } from "lucide-react";
import { initGrpcClient } from "./grpcClient";

const DashboardPage = lazy(() => import("./pages/Dashboard"));
const VaultPage = lazy(() => import("./pages/Vault"));
const ProcessesPage = lazy(() => import("./pages/Processes"));
const TerminalPage = lazy(() => import("./pages/Terminal"));
const EnvironmentsPage = lazy(() => import("./pages/Environments"));

interface SidebarProps {
  isCollapsed: boolean;
  onToggle: () => void;
}

function Sidebar({ isCollapsed, onToggle }: SidebarProps) {
  const location = useLocation();

  const links = [
    { to: "/", icon: <Activity size={20} />, label: "Dashboard" },
    { to: "/vault", icon: <KeyRound size={20} />, label: "Vault" },
    { to: "/environments", icon: <Globe size={20} />, label: "Environments" },
    { to: "/processes", icon: <Server size={20} />, label: "Processes" },
    { to: "/terminal", icon: <Terminal size={20} />, label: "Terminal" },
  ];

  return (
    <div style={{
      width: isCollapsed ? "72px" : "240px",
      backgroundColor: "var(--bg-tertiary)",
      borderRight: "1px solid var(--border-color)",
      display: "flex",
      flexDirection: "column",
      padding: "20px 0",
      height: "100vh",
      transition: "width 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
      position: "relative",
      flexShrink: 0
    }}>
      <div style={{ 
        padding: "0 24px", 
        marginBottom: "32px",
        display: "flex",
        alignItems: "center",
        justifyContent: isCollapsed ? "center" : "space-between",
        height: "40px"
      }}>
        {!isCollapsed ? (
          <h2 className="gradient-text" style={{ margin: 0, fontSize: "1.25rem", whiteSpace: "nowrap", overflow: "hidden" }}>Command Center</h2>
        ) : (
          <Activity size={24} style={{ color: "var(--accent-primary)" }} />
        )}
      </div>
      
      <nav style={{ display: "flex", flexDirection: "column", gap: "8px", padding: "0 12px", flex: 1 }}>
        {links.map((link) => {
          const isActive = location.pathname === link.to;
          return (
            <Link
              key={link.to}
              to={link.to}
              title={isCollapsed ? link.label : undefined}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: isCollapsed ? "center" : "flex-start",
                gap: isCollapsed ? "0" : "12px",
                padding: "10px 16px",
                borderRadius: "8px",
                color: isActive ? "var(--text-primary)" : "var(--text-secondary)",
                backgroundColor: isActive ? "var(--bg-glass-hover)" : "transparent",
                fontWeight: isActive ? 600 : 400,
                transition: "all 0.2s",
                height: "44px"
              }}
            >
              <div style={{ 
                color: isActive ? "var(--accent-primary)" : "inherit",
                display: "flex",
                alignItems: "center",
                justifyContent: "center"
              }}>
                {link.icon}
              </div>
              {!isCollapsed && <span style={{ whiteSpace: "nowrap", overflow: "hidden" }}>{link.label}</span>}
            </Link>
          );
        })}
      </nav>

      <div style={{ padding: "0 12px", display: "flex", justifyContent: "center" }}>
        <button
          onClick={onToggle}
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: "100%",
            height: "40px",
            borderRadius: "8px",
            backgroundColor: "rgba(255, 255, 255, 0.03)",
            border: "1px solid var(--border-color)",
            color: "var(--text-secondary)",
            transition: "all 0.2s"
          }}
          title={isCollapsed ? "Expand Sidebar" : "Collapse Sidebar"}
        >
          {isCollapsed ? <ChevronRight size={20} /> : <ChevronLeft size={20} />}
        </button>
      </div>
    </div>
  );
}

export default function App() {
  const [initialized, setInitialized] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(false);

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
      <Sidebar isCollapsed={isCollapsed} onToggle={() => setIsCollapsed(!isCollapsed)} />
      <main style={{ flex: 1, overflowY: "auto", padding: "32px" }}>
        <Suspense fallback={<p style={{ color: "var(--text-secondary)" }}>Loading Page...</p>}>
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/vault" element={<VaultPage />} />
            <Route path="/environments" element={<EnvironmentsPage />} />
            <Route path="/processes" element={<ProcessesPage />} />
            <Route path="/terminal" element={<TerminalPage />} />
          </Routes>
        </Suspense>
      </main>
    </div>
  );
}
