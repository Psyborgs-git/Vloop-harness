import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { WorkflowEventFrame } from "../lib/api";

/**
 * Reusable subscription to the Control_Plane normalized workflow-event stream.
 *
 * The Control_Plane runs a WebSocket push channel (`cp/ws_server.py`) that
 * fans out every normalized `WorkflowEvent` (`core/event_router.py`) as a JSON
 * text frame — run/step transitions, approval-required, budget/rate status,
 * etc. (Requirements 4.1, 20.4). This hook owns one connection, parses frames
 * into {@link WorkflowEventFrame}s, auto-reconnects on close, and tears the
 * socket down on unmount.
 *
 * It is intentionally generic so the sibling orchestration views
 * (approvals/budgets/checkpoints/schedule) can reuse it: it returns the whole
 * event stream and lets callers filter by `type` or `run_id`.
 */

export type WorkflowEventStreamStatus = "connecting" | "open" | "closed";

export interface UseWorkflowEventsOptions {
  /** Override the resolved WebSocket URL (otherwise derived from the page). */
  url?: string;
  /** When false, the hook stays disconnected (useful to defer connecting). */
  enabled?: boolean;
  /** Cap the in-memory ring buffer of events (default 500). */
  maxEvents?: number;
  /** Delay before attempting to reconnect after a close (default 2000ms). */
  reconnectDelayMs?: number;
}

export interface UseWorkflowEventsResult {
  /** All events received so far, oldest first (capped at `maxEvents`). */
  events: WorkflowEventFrame[];
  /** Current connection status. */
  status: WorkflowEventStreamStatus;
  /** Last connection/parse error message, if any. */
  lastError: string | null;
  /** The resolved WebSocket URL in use. */
  url: string;
  /** Clear the buffered events. */
  clear: () => void;
  /** Convenience filter: events attributed to a single run, in `seq` order. */
  eventsForRun: (runId: string) => WorkflowEventFrame[];
}

const DEFAULT_WS_PATH = "/ws/workflow-events";
const DEFAULT_MAX_EVENTS = 500;
const DEFAULT_RECONNECT_DELAY_MS = 2000;

type ViteEnv = Record<string, string | boolean | undefined>;

function readEnv(): ViteEnv {
  try {
    return (import.meta as unknown as { env?: ViteEnv }).env ?? {};
  } catch {
    return {};
  }
}

/**
 * Resolve the workflow-event WebSocket URL.
 *
 * Defaults to the same host as the page with a `ws://`/`wss://` scheme (the
 * Frontend is served by the Control_Plane HTTP shell), targeting the
 * `/ws/workflow-events` upgrade path. The Control_Plane WebSocket server
 * (`cp/ws_server.py`) upgrades on any path, so the path is a stable label.
 * Every part can be overridden via Vite env vars for deployments where the
 * push channel listens on a different host/port:
 *   - `VITE_VLOOP_WS_URL`  — full override, wins outright
 *   - `VITE_VLOOP_WS_HOST` — host (defaults to `window.location.hostname`)
 *   - `VITE_VLOOP_WS_PORT` — port (defaults to `window.location.port`)
 *   - `VITE_VLOOP_WS_PATH` — path (defaults to `/ws/workflow-events`)
 */
export function resolveWorkflowEventsUrl(): string {
  const env = readEnv();

  const explicit = env.VITE_VLOOP_WS_URL;
  if (typeof explicit === "string" && explicit) {
    return explicit;
  }

  const loc = window.location;
  const scheme = loc.protocol === "https:" ? "wss:" : "ws:";

  const host =
    (typeof env.VITE_VLOOP_WS_HOST === "string" && env.VITE_VLOOP_WS_HOST) ||
    loc.hostname;
  const port =
    (typeof env.VITE_VLOOP_WS_PORT === "string" && env.VITE_VLOOP_WS_PORT) ||
    loc.port ||
    "";
  const path =
    (typeof env.VITE_VLOOP_WS_PATH === "string" && env.VITE_VLOOP_WS_PATH) ||
    DEFAULT_WS_PATH;

  const authority = port ? `${host}:${port}` : host;
  return `${scheme}//${authority}${path}`;
}

function parseFrame(data: unknown): WorkflowEventFrame | null {
  if (typeof data !== "string") {
    return null;
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(data);
  } catch {
    return null;
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    return null;
  }
  const record = parsed as Record<string, unknown>;
  const runId = record.run_id;
  const type = record.type;
  // A workflow event is only meaningful when attributed to a run and typed.
  if (typeof runId !== "string" || typeof type !== "string") {
    return null;
  }
  const payload =
    record.payload && typeof record.payload === "object" && !Array.isArray(record.payload)
      ? (record.payload as Record<string, unknown>)
      : {};
  return {
    run_id: runId,
    seq: typeof record.seq === "number" ? record.seq : 0,
    type,
    step_id: typeof record.step_id === "string" ? record.step_id : null,
    message: typeof record.message === "string" ? record.message : "",
    payload,
    created_at: typeof record.created_at === "string" ? record.created_at : "",
  };
}

export function useWorkflowEvents(
  options: UseWorkflowEventsOptions = {},
): UseWorkflowEventsResult {
  const {
    enabled = true,
    maxEvents = DEFAULT_MAX_EVENTS,
    reconnectDelayMs = DEFAULT_RECONNECT_DELAY_MS,
  } = options;

  const url = useMemo(
    () => options.url ?? resolveWorkflowEventsUrl(),
    [options.url],
  );

  const [events, setEvents] = useState<WorkflowEventFrame[]>([]);
  const [status, setStatus] = useState<WorkflowEventStreamStatus>("closed");
  const [lastError, setLastError] = useState<string | null>(null);

  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const teardownRef = useRef(false);

  const clear = useCallback(() => setEvents([]), []);

  const eventsForRun = useCallback(
    (runId: string) =>
      events
        .filter((event) => event.run_id === runId)
        .sort((a, b) => a.seq - b.seq),
    [events],
  );

  useEffect(() => {
    if (!enabled) {
      setStatus("closed");
      return;
    }

    teardownRef.current = false;

    const scheduleReconnect = () => {
      if (teardownRef.current || reconnectTimerRef.current !== null) {
        return;
      }
      reconnectTimerRef.current = window.setTimeout(() => {
        reconnectTimerRef.current = null;
        connect();
      }, reconnectDelayMs);
    };

    const connect = () => {
      if (teardownRef.current) {
        return;
      }
      setStatus("connecting");

      let socket: WebSocket;
      try {
        socket = new WebSocket(url);
      } catch (err: unknown) {
        setLastError(err instanceof Error ? err.message : String(err));
        scheduleReconnect();
        return;
      }
      socketRef.current = socket;

      socket.onopen = () => {
        setStatus("open");
        setLastError(null);
      };

      socket.onmessage = (event: MessageEvent) => {
        const frame = parseFrame(event.data);
        if (!frame) {
          return;
        }
        setEvents((prev) => {
          const next = [...prev, frame];
          return next.length > maxEvents
            ? next.slice(next.length - maxEvents)
            : next;
        });
      };

      socket.onerror = () => {
        setLastError("workflow event stream connection error");
      };

      socket.onclose = () => {
        socketRef.current = null;
        setStatus("closed");
        if (!teardownRef.current) {
          scheduleReconnect();
        }
      };
    };

    connect();

    return () => {
      teardownRef.current = true;
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      const socket = socketRef.current;
      socketRef.current = null;
      if (socket) {
        socket.onopen = null;
        socket.onmessage = null;
        socket.onerror = null;
        socket.onclose = null;
        try {
          socket.close();
        } catch {
          /* ignore */
        }
      }
    };
  }, [url, enabled, maxEvents, reconnectDelayMs]);

  return { events, status, lastError, url, clear, eventsForRun };
}
