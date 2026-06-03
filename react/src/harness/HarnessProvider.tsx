/**
 * HarnessProvider — wraps every component app.
 *
 * - Reads window.__HARNESS__ for config
 * - Falls back to Tauri command if __HARNESS__ is not available (static mode)
 * - Opens a WebSocket to the Python component
 * - Keeps state in sync via "state_update" messages
 * - Exposes HarnessContext to the subtree
 */

import {
    createContext,
    useCallback,
    useEffect,
    useMemo,
    useRef,
    useState,
    type ReactNode,
} from "react";
import type { HarnessContext, WSMessage } from "./types";

export const HarnessCtx = createContext<HarnessContext | null>(null);

interface Props {
    children: ReactNode;
}

interface HarnessConfig {
    component_id: string;
    api_url: string;
    ws_url: string;
    initial_state: Record<string, unknown>;
    permissions: string[];
}

// Legacy interface for window.__HARNESS__ (uppercase fields)
interface LegacyHarnessConfig {
    COMPONENT_ID: string;
    API_URL: string;
    WS_URL: string;
    INITIAL_STATE: Record<string, unknown>;
    PERMISSIONS: string[];
}

// Runtime type guard for legacy config
function isLegacyConfig(obj: unknown): obj is LegacyHarnessConfig {
    return typeof obj === 'object' && obj !== null &&
        'COMPONENT_ID' in obj && typeof (obj as LegacyHarnessConfig).COMPONENT_ID === 'string' &&
        'API_URL' in obj && typeof (obj as LegacyHarnessConfig).API_URL === 'string' &&
        'WS_URL' in obj && typeof (obj as LegacyHarnessConfig).WS_URL === 'string' &&
        'INITIAL_STATE' in obj && typeof (obj as LegacyHarnessConfig).INITIAL_STATE === 'object' &&
        'PERMISSIONS' in obj && Array.isArray((obj as LegacyHarnessConfig).PERMISSIONS);
}

function convertLegacyConfig(legacy: LegacyHarnessConfig): HarnessConfig {
    return {
        component_id: legacy.COMPONENT_ID,
        api_url: legacy.API_URL,
        ws_url: legacy.WS_URL,
        initial_state: legacy.INITIAL_STATE,
        permissions: legacy.PERMISSIONS,
    };
}

// Configuration fallback function (single source of truth)
function getFallbackConfig(): HarnessConfig {
    return {
        component_id: 'root',
        api_url: 'http://127.0.0.1:9100/api/root',
        ws_url: 'ws://127.0.0.1:9100/ws/root',
        initial_state: {},
        permissions: [],
    };
}

const MAX_RETRIES = 5;
const BASE_RETRY_DELAY = 1000; // 1 second
const MAX_RETRY_DELAY = 30000; // 30 seconds

export function HarnessProvider({ children }: Props) {
    const cfg = useMemo<HarnessConfig>(() => {
        if (window.__HARNESS__ && isLegacyConfig(window.__HARNESS__)) {
            return convertLegacyConfig(window.__HARNESS__);
        }
        return getFallbackConfig();
    }, []);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [retryCount, setRetryCount] = useState(0);

    const [state, setState] = useState<Record<string, unknown>>(
        cfg?.initial_state ?? {}
    );
    const [connected, setConnected] = useState(false);
    const wsRef = useRef<WebSocket | null>(null);
    const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

    // Use ref for config to avoid unnecessary reconnections
    const configRef = useRef(cfg);
    useEffect(() => {
        configRef.current = cfg;
    }, [cfg]);

    // Load config from Tauri if not available (static mode)
    useEffect(() => {
        // Since we're using backend URL injection, we don't need Tauri command
        // The backend will inject window.__HARNESS__ variables
    }, [cfg, isLoading, error]);

    const connect = useCallback(() => {
        const currentCfg = configRef.current;
        if (!currentCfg?.ws_url || isLoading || error) return;

        // Don't attempt connection if max retries reached
        if (retryCount >= MAX_RETRIES) {
            console.error('Max connection retries reached');
            return;
        }

        const ws = new WebSocket(currentCfg.ws_url);
        wsRef.current = ws;

        ws.onopen = () => {
            setConnected(true);
            setRetryCount(0); // Reset retry count on successful connection
            setError(null);
        };

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

            // Implement exponential backoff with max delay
            if (retryCount < MAX_RETRIES) {
                const delay = Math.min(
                    BASE_RETRY_DELAY * Math.pow(2, retryCount),
                    MAX_RETRY_DELAY
                );

                reconnectTimer.current = setTimeout(() => {
                    setRetryCount(prev => prev + 1);
                    connect();
                }, delay);
            } else {
                setError('Connection failed after maximum retry attempts');
            }
        };

        ws.onerror = () => {
            ws.close();
        };
    }, [isLoading, error, retryCount]);

    useEffect(() => {
        if (!isLoading && !error && cfg) {
            connect();
        }
        return () => {
            reconnectTimer.current && clearTimeout(reconnectTimer.current);
            wsRef.current?.close();
        };
    }, [connect, isLoading, error, cfg]);

    const emit = useCallback((eventName: string, payload?: unknown) => {
        const ws = wsRef.current;
        if (ws?.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: eventName, data: payload ?? null }));
        }
    }, []);

    const ctx: HarnessContext = {
        state,
        props: cfg?.initial_state ?? {},
        emit,
        connected,
    };

    // Show loading state
    if (isLoading) {
        return <div style={{
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            height: '100vh',
            fontFamily: 'system-ui, sans-serif',
            flexDirection: 'column',
            gap: '1rem'
        }}>
            <div>Loading Harness...</div>
        </div>;
    }

    // Show error state
    if (error) {
        return <div style={{
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            height: '100vh',
            fontFamily: 'system-ui, sans-serif',
            flexDirection: 'column',
            gap: '1rem',
            padding: '2rem',
            textAlign: 'center'
        }}>
            <div style={{ color: '#d32f2f', fontSize: '1.2rem' }}>
                ⚠️ Error
            </div>
            <div>{error}</div>
            <button
                onClick={() => {
                    setError(null);
                    setRetryCount(0);
                    if (!cfg) {
                        // Retry config loading
                        setIsLoading(true);
                    } else {
                        // Retry connection
                        connect();
                    }
                }}
                style={{
                    padding: '0.5rem 1rem',
                    background: '#1976d2',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer'
                }}
            >
                Retry
            </button>
        </div>;
    }

    return <HarnessCtx.Provider value={ctx}>{children}</HarnessCtx.Provider>;
}
