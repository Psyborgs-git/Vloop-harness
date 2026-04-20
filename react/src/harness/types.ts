/** Types shared across all harness React apps. */

export interface HarnessConfig {
  COMPONENT_ID: string;
  API_URL: string;
  WS_URL: string;
  INITIAL_STATE: Record<string, unknown>;
  PERMISSIONS: string[];
}

export type WSMessage =
  | { type: "state_update"; data: Record<string, unknown> }
  | { type: "reloading"; data: unknown }
  | { type: string; data: unknown };

export interface HarnessContext {
  /** Live state from Python — auto-updated via WebSocket. */
  state: Record<string, unknown>;
  /** Read-only props passed down from the Python parent. */
  props: Record<string, unknown>;
  /** Send a named event to the Python component. */
  emit: (eventName: string, payload?: unknown) => void;
  /** True while the WebSocket is connected. */
  connected: boolean;
}

declare global {
  interface Window {
    __HARNESS__: HarnessConfig;
  }
}
