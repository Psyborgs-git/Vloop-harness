import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import * as api from "./api";
import type { ClientTelemetryData, ClientTelemetryEvent, DashboardActionDefinition } from "./types";

const LEARNING_STORAGE_KEY = "vloop_client_action_learning_v1";
const CLIENT_ID_STORAGE_KEY = "vloop_client_id";
const FLUSH_INTERVAL_MS = 5000;
const MAX_BUFFERED_EVENTS = 50;
const RECENCY_HALF_LIFE_MS = 1000 * 60 * 60 * 24 * 7;

interface ActionLearningStats {
  actionId: string;
  count: number;
  lastUsedAt: number;
  screenCounts: Record<string, number>;
}

interface StoredLearningState {
  version: 1;
  actions: Record<string, ActionLearningStats>;
}

interface TrackOptions {
  screen?: string;
  actionId?: string;
  data?: ClientTelemetryData;
  componentId?: string | null;
}

interface AnalyticsContextValue {
  screen: string;
  setScreen: (screen: string, data?: ClientTelemetryData) => void;
  track: (eventType: string, options?: TrackOptions) => void;
  trackAction: (actionId: string, options?: TrackOptions) => void;
  rankActions: (
    actions: DashboardActionDefinition[],
    options?: { screen?: string; limit?: number },
  ) => DashboardActionDefinition[];
}

const AnalyticsContext = createContext<AnalyticsContextValue | null>(null);

function createClientId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `client-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function getClientId(): string {
  const existing = localStorage.getItem(CLIENT_ID_STORAGE_KEY);
  if (existing) return existing;
  const next = createClientId();
  localStorage.setItem(CLIENT_ID_STORAGE_KEY, next);
  return next;
}

function loadLearningState(): StoredLearningState {
  try {
    const raw = localStorage.getItem(LEARNING_STORAGE_KEY);
    if (!raw) return { version: 1, actions: {} };
    const parsed = JSON.parse(raw) as StoredLearningState;
    if (parsed.version !== 1 || !parsed.actions) return { version: 1, actions: {} };
    return parsed;
  } catch {
    return { version: 1, actions: {} };
  }
}

function saveLearningState(state: StoredLearningState) {
  localStorage.setItem(LEARNING_STORAGE_KEY, JSON.stringify(state));
}

function actionScore(action: DashboardActionDefinition, stats: ActionLearningStats | undefined, screen: string): number {
  const base = 1000 - action.baselineRank;
  if (!stats) return base;
  const age = Math.max(0, Date.now() - stats.lastUsedAt);
  const recency = Math.pow(0.5, age / RECENCY_HALF_LIFE_MS);
  const frequency = Math.log1p(stats.count) * 25;
  const screenAffinity = Math.log1p(stats.screenCounts[screen] ?? 0) * 35;
  return base + frequency + screenAffinity + recency * 50;
}

export function AnalyticsProvider({ children }: { children: React.ReactNode }) {
  const [screen, setScreenState] = useState("dashboard.chat");
  const [learning, setLearning] = useState<StoredLearningState>(() => loadLearningState());
  const clientIdRef = useRef<string | null>(null);
  const queueRef = useRef<ClientTelemetryEvent[]>([]);

  useEffect(() => {
    clientIdRef.current = getClientId();
  }, []);

  useEffect(() => {
    saveLearningState(learning);
  }, [learning]);

  const flush = useCallback(async () => {
    if (queueRef.current.length === 0) return;
    const batch = queueRef.current.splice(0, MAX_BUFFERED_EVENTS);
    try {
      await api.recordTelemetryEvents(batch);
    } catch {
      queueRef.current = [...batch.slice(-MAX_BUFFERED_EVENTS), ...queueRef.current].slice(-MAX_BUFFERED_EVENTS);
    }
  }, []);

  useEffect(() => {
    const timer = window.setInterval(flush, FLUSH_INTERVAL_MS);
    const onVisibility = () => {
      if (document.visibilityState === "hidden") void flush();
    };
    window.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("beforeunload", () => void flush());
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("visibilitychange", onVisibility);
    };
  }, [flush]);

  const track = useCallback(
    (eventType: string, options: TrackOptions = {}) => {
      const activeScreen = options.screen ?? screen;
      queueRef.current.push({
        event_type: eventType,
        component_id: options.componentId ?? null,
        occurred_at: new Date().toISOString(),
        data: {
          ...(options.data ?? {}),
          action_id: options.actionId,
          screen: activeScreen,
          client_id: clientIdRef.current,
          path: window.location.pathname,
        },
      });
      if (queueRef.current.length >= MAX_BUFFERED_EVENTS) void flush();
    },
    [flush, screen],
  );

  const setScreen = useCallback(
    (nextScreen: string, data?: ClientTelemetryData) => {
      setScreenState((prev) => {
        if (prev !== nextScreen) {
          track("screen_view", { screen: nextScreen, data: { previous_screen: prev, ...(data ?? {}) } });
        }
        return nextScreen;
      });
    },
    [track],
  );

  const trackAction = useCallback(
    (actionId: string, options: TrackOptions = {}) => {
      const activeScreen = options.screen ?? screen;
      const now = Date.now();
      setLearning((prev) => {
        const current = prev.actions[actionId] ?? {
          actionId,
          count: 0,
          lastUsedAt: 0,
          screenCounts: {},
        };
        return {
          version: 1,
          actions: {
            ...prev.actions,
            [actionId]: {
              ...current,
              count: current.count + 1,
              lastUsedAt: now,
              screenCounts: {
                ...current.screenCounts,
                [activeScreen]: (current.screenCounts[activeScreen] ?? 0) + 1,
              },
            },
          },
        };
      });
      track("action_click", { ...options, actionId, screen: activeScreen });
    },
    [screen, track],
  );

  const rankActions = useCallback(
    (
      actions: DashboardActionDefinition[],
      options: { screen?: string; limit?: number } = {},
    ) => {
      const activeScreen = options.screen ?? screen;
      const ranked = [...actions].sort((a, b) => (
        actionScore(b, learning.actions[b.id], activeScreen) - actionScore(a, learning.actions[a.id], activeScreen)
      ));
      return typeof options.limit === "number" ? ranked.slice(0, options.limit) : ranked;
    },
    [learning.actions, screen],
  );

  const value = useMemo(
    () => ({ screen, setScreen, track, trackAction, rankActions }),
    [rankActions, screen, setScreen, track, trackAction],
  );

  return <AnalyticsContext.Provider value={value}>{children}</AnalyticsContext.Provider>;
}

export function useAnalytics(): AnalyticsContextValue {
  const value = useContext(AnalyticsContext);
  if (!value) {
    throw new Error("useAnalytics must be used inside AnalyticsProvider");
  }
  return value;
}
