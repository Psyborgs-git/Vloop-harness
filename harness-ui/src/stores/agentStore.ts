import { create } from "zustand";

export interface AgentRun {
  id: string;
  agent_name: string;
  agent_loop: string;
  task: string;
  status: string;
  created_at: string;
  finished_at?: string;
}

export interface AgentStep {
  id: string;
  run_id: string;
  step_index: number;
  step_type: string;
  content: string;
  created_at: string;
}

interface AgentState {
  runs: AgentRun[];
  selectedRun: AgentRun | null;
  steps: AgentStep[];
  streaming: boolean;
  setRuns: (runs: AgentRun[]) => void;
  selectRun: (run: AgentRun | null) => void;
  setSteps: (steps: AgentStep[]) => void;
  setStreaming: (v: boolean) => void;
  addStep: (step: AgentStep) => void;
}

export const useAgentStore = create<AgentState>((set) => ({
  runs: [],
  selectedRun: null,
  steps: [],
  streaming: false,
  setRuns: (runs) => set({ runs }),
  selectRun: (selectedRun) => set({ selectedRun, steps: [] }),
  setSteps: (steps) => set({ steps }),
  setStreaming: (streaming) => set({ streaming }),
  addStep: (step) => set((s) => ({ steps: [...s.steps, step] })),
}));
