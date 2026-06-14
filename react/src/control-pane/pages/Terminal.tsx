import { useEffect, useState, useRef } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
import { terminalClient } from "../grpcClient";

export default function TerminalPage() {
  const [sessions, setSessions] = useState<string[]>([]);
  const [selectedSession, setSelectedSession] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [newSessionId, setNewSessionId] = useState("");
  const [newSessionCmd, setNewSessionCmd] = useState("/bin/bash");
  const [newSessionCwd, setNewSessionCwd] = useState("/");

  const terminalContainerRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<Terminal | null>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);

  const fetchSessions = async () => {
    try {
      const res = await terminalClient.listSessions({});
      setSessions(res.sessionIds);
      if (res.sessionIds.length > 0 && !selectedSession) {
        setSelectedSession(res.sessionIds[0]);
      }
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchSessions();
    const interval = setInterval(fetchSessions, 5000);
    return () => clearInterval(interval);
  }, []);

  // Initialize xterm
  useEffect(() => {
    if (!terminalContainerRef.current) return;

    const term = new Terminal({
      theme: { background: "#000000" },
      fontFamily: "monospace",
      cursorBlink: true,
    });
    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);
    term.open(terminalContainerRef.current);
    fitAddon.fit();

    termRef.current = term;
    fitAddonRef.current = fitAddon;

    const handleResize = () => fitAddon.fit();
    window.addEventListener("resize", handleResize);

    // Send input to gRPC
    const dataDisposable = term.onData((data) => {
      if (selectedSession) {
        terminalClient.writeStdin({ sessionId: selectedSession, data });
      }
    });

    return () => {
      window.removeEventListener("resize", handleResize);
      dataDisposable.dispose();
      term.dispose();
    };
  }, [selectedSession]);

  // Read buffer loop
  useEffect(() => {
    if (!selectedSession || !termRef.current) return;

    // Clear terminal when switching sessions
    termRef.current.clear();

    const fetchBuffer = async () => {
      try {
        const res = await terminalClient.readBuffer({ sessionId: selectedSession });
        if (res.success && res.data) {
          termRef.current?.write(res.data);
        }
      } catch (e) {
        console.error(e);
      }
    };

    const int = setInterval(fetchBuffer, 100);
    return () => clearInterval(int);
  }, [selectedSession]);

  const handleCreateSession = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSessionId || !newSessionCmd) return;
    
    try {
      await terminalClient.startSession({
        sessionId: newSessionId,
        command: newSessionCmd,
        args: [],
        cwd: newSessionCwd
      });
      setSessions((prev) => [...prev, newSessionId]);
      setSelectedSession(newSessionId);
      setIsCreating(false);
      setNewSessionId("");
    } catch (e) {
      console.error("Failed to create session", e);
    }
  };

  return (
    <div className="animate-fade-in" style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
        <h1 style={{ margin: 0 }}>Live Terminals</h1>
        <button
          onClick={() => setIsCreating(true)}
          style={{
            padding: "8px 16px",
            background: "var(--accent-primary)",
            color: "#fff",
            border: "none",
            borderRadius: "6px",
            cursor: "pointer",
            fontWeight: "bold",
          }}
        >
          + Create Session
        </button>
      </div>
      <p style={{ color: "var(--text-secondary)", marginBottom: "24px" }}>View output from agent-controlled shell sessions.</p>

      {isCreating && (
        <div style={{ marginBottom: "24px", padding: "16px", background: "var(--bg-glass)", borderRadius: "8px", border: "1px solid var(--border-color)" }}>
          <h3 style={{ marginTop: 0 }}>New Session</h3>
          <form onSubmit={handleCreateSession} style={{ display: "flex", gap: "16px", alignItems: "flex-end" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
              <label style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>Session ID</label>
              <input value={newSessionId} onChange={(e) => setNewSessionId(e.target.value)} required style={{ padding: "8px", borderRadius: "4px", background: "var(--bg-tertiary)", color: "#fff", border: "1px solid var(--border-color)" }} placeholder="my-session-1" />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
              <label style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>Command</label>
              <input value={newSessionCmd} onChange={(e) => setNewSessionCmd(e.target.value)} required style={{ padding: "8px", borderRadius: "4px", background: "var(--bg-tertiary)", color: "#fff", border: "1px solid var(--border-color)" }} />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
              <label style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>CWD</label>
              <input value={newSessionCwd} onChange={(e) => setNewSessionCwd(e.target.value)} required style={{ padding: "8px", borderRadius: "4px", background: "var(--bg-tertiary)", color: "#fff", border: "1px solid var(--border-color)" }} />
            </div>
            <button type="submit" style={{ padding: "8px 16px", background: "var(--accent-primary)", color: "#fff", border: "none", borderRadius: "4px", cursor: "pointer" }}>Start</button>
            <button type="button" onClick={() => setIsCreating(false)} style={{ padding: "8px 16px", background: "var(--bg-tertiary)", color: "var(--text-secondary)", border: "1px solid var(--border-color)", borderRadius: "4px", cursor: "pointer" }}>Cancel</button>
          </form>
        </div>
      )}

      <div style={{ display: "flex", gap: "24px", flex: 1, overflow: "hidden" }}>
        
        {/* Sidebar for Sessions */}
        <div className="glass-panel" style={{ width: "250px", display: "flex", flexDirection: "column", overflowY: "auto", padding: "16px" }}>
          <h3 style={{ fontSize: "0.875rem", textTransform: "uppercase", color: "var(--text-secondary)", marginBottom: "16px" }}>Active Sessions</h3>
          {sessions.length === 0 ? (
            <p style={{ color: "var(--text-tertiary)", fontSize: "0.875rem" }}>No active sessions.</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              {sessions.map(id => (
                <button
                  key={id}
                  onClick={() => setSelectedSession(id)}
                  style={{
                    textAlign: "left",
                    padding: "12px",
                    borderRadius: "8px",
                    background: selectedSession === id ? "var(--bg-glass-hover)" : "transparent",
                    color: selectedSession === id ? "white" : "var(--text-secondary)",
                    border: "1px solid",
                    borderColor: selectedSession === id ? "var(--border-highlight)" : "transparent",
                  }}
                >
                  <div style={{ fontSize: "0.875rem", fontFamily: "monospace", overflow: "hidden", textOverflow: "ellipsis" }}>{id}</div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Terminal Window */}
        <div className="glass-panel" style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", background: "#000", padding: "8px" }}>
          <div ref={terminalContainerRef} style={{ flex: 1, overflow: "hidden" }}></div>
        </div>

      </div>
    </div>
  );
}
