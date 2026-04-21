/**
 * HarnessProvider — wraps every component app.
 *
 * - Reads window.__HARNESS__ for config
 * - Opens a WebSocket to the Python component
 * - Keeps state in sync via "state_update" messages
 * - Exposes HarnessContext to the subtree
 */

import React, {
  createContext,
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { HarnessContext, WSMessage } from "./types";

export const HarnessCtx = createContext<HarnessContext | null>(null);

interface Props {
  children: ReactNode;
}

export function HarnessProvider({ children }: Props) {
  const cfg = window.__HARNESS__;

  const [state, setState] = useState<Record<string, unknown>>(
    cfg?.INITIAL_STATE ?? {}
  );
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = useCallback(() => {
    if (!cfg?.WS_URL) return;

    const ws = new WebSocket(cfg.WS_URL);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);

    ws.onmessage = (ev) => {
      try {
        const msg: WSMessage = JSON.parse(ev.data as string);
        if (msg.type === "state_update") {
          setState(msg.data as Record<string, unknown>);
        } else if (msg.type === "reloading") {
          setConnected(false);
        }
      } catch {
        // non-JSON frame — ignore
      }
    };

    ws.onclose = () => {
      setConnected(false);
      // Reconnect after 1 s
      reconnectTimer.current = setTimeout(connect, 3000);
    };

    ws.onerror = () => ws.close();
  }, [cfg?.WS_URL]);

  useEffect(() => {
    connect();
    return () => {
      reconnectTimer.current && clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const emit = useCallback((eventName: string, payload?: unknown) => {
    const ws = wsRef.current;
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: eventName, data: payload ?? null }));
    }
  }, []);

  const ctx: HarnessContext = {
    state,
    props: cfg?.INITIAL_STATE ?? {},
    emit,
    connected,
  };

  return <HarnessCtx.Provider value={ctx}>{children}</HarnessCtx.Provider>;
}
