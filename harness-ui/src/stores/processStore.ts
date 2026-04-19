import { create } from "zustand";

export interface ProcessInfo {
  id: string;
  name: string;
  command: string;
  status: string;
  pid?: number;
  port?: number;
  started_at?: string;
}

interface ProcessState {
  processes: ProcessInfo[];
  setProcesses: (p: ProcessInfo[]) => void;
  updateProcess: (id: string, updates: Partial<ProcessInfo>) => void;
}

export const useProcessStore = create<ProcessState>((set) => ({
  processes: [],
  setProcesses: (processes) => set({ processes }),
  updateProcess: (id, updates) =>
    set((s) => ({
      processes: s.processes.map((p) =>
        p.id === id ? { ...p, ...updates } : p
      ),
    })),
}));
