import { create } from "zustand";

export interface TerminalSession {
  id: string;
  shell: string;
  cwd: string;
  pid?: number;
  status: string;
}

interface TerminalState {
  sessions: TerminalSession[];
  activeSessionId: string | null;
  setSessions: (sessions: TerminalSession[]) => void;
  setActive: (id: string | null) => void;
  addSession: (session: TerminalSession) => void;
  removeSession: (id: string) => void;
}

export const useTerminalStore = create<TerminalState>((set) => ({
  sessions: [],
  activeSessionId: null,
  setSessions: (sessions) => set({ sessions }),
  setActive: (activeSessionId) => set({ activeSessionId }),
  addSession: (session) =>
    set((s) => ({ sessions: [...s.sessions, session] })),
  removeSession: (id) =>
    set((s) => ({
      sessions: s.sessions.filter((se) => se.id !== id),
      activeSessionId: s.activeSessionId === id ? null : s.activeSessionId,
    })),
}));
