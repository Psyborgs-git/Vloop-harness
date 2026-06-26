import { useCallback, useEffect, useRef, useState } from "react";
import {
  DEFAULT_PROVIDER_CATALOG,
  getBootstrap,
  getErrorMessage,
  getSystemSnapshot,
  shutdownApp,
  sortAgents,
  sortInvocations,
  sortProviders,
  type AgentConfig,
  type BootstrapPayload,
  type InvocationRecord,
  type ProviderConfig,
  type SystemSnapshot,
} from "../lib/api";

const EMPTY_BOOTSTRAP: BootstrapPayload = {
  providers: [],
  agents: [],
  invocations: [],
  providerCatalog: DEFAULT_PROVIDER_CATALOG,
  agentTemplates: [],
  apiAvailable: false,
  source: "fallback",
  warning: null,
};

type Theme = "light" | "dark" | "auto";

export function useAppData() {
  const [bootstrap, setBootstrap] = useState<BootstrapPayload>(EMPTY_BOOTSTRAP);
  const [system, setSystem] = useState<SystemSnapshot | null>(null);
  const [bootstrapLoading, setBootstrapLoading] = useState(true);
  const [systemLoading, setSystemLoading] = useState(true);
  const [bootstrapError, setBootstrapError] = useState<string | null>(null);
  const [systemError, setSystemError] = useState<string | null>(null);
  const [lastRefreshAt, setLastRefreshAt] = useState<number | null>(null);
  const [shuttingDown, setShuttingDown] = useState(false);
  const [shutdownError, setShutdownError] = useState<string | null>(null);

  const [theme, setTheme] = useState<Theme>(() => {
    const stored = localStorage.getItem("vloop-theme");
    return stored === "light" || stored === "dark" || stored === "auto" ? stored : "auto";
  });

  // Apply theme attribute to document
  useEffect(() => {
    localStorage.setItem("vloop-theme", theme);
    if (theme === "auto") {
      document.documentElement.removeAttribute("data-theme");
    } else {
      document.documentElement.setAttribute("data-theme", theme);
    }
  }, [theme]);

  const handleQuit = useCallback(async () => {
    if (shuttingDown) return;
    setShuttingDown(true);
    setShutdownError(null);
    try {
      await shutdownApp();
    } catch (error) {
      setShuttingDown(false);
      setShutdownError(getErrorMessage(error));
    }
  }, [shuttingDown]);

  const refreshBootstrap = useCallback(async (silent = false) => {
    if (!silent) setBootstrapLoading(true);
    try {
      const next = await getBootstrap();
      setBootstrap(next);
      setBootstrapError(null);
      setLastRefreshAt(Date.now());
    } catch (error) {
      setBootstrapError(getErrorMessage(error));
    } finally {
      if (!silent) setBootstrapLoading(false);
    }
  }, []);

  const refreshSystem = useCallback(async (silent = false) => {
    if (!silent) setSystemLoading(true);
    try {
      const next = await getSystemSnapshot();
      setSystem(next);
      setSystemError(null);
      setLastRefreshAt(Date.now());
    } catch (error) {
      setSystemError(getErrorMessage(error));
    } finally {
      if (!silent) setSystemLoading(false);
    }
  }, []);

  const refreshAll = useCallback(async () => {
    await Promise.all([refreshBootstrap(false), refreshSystem(false)]);
  }, [refreshBootstrap, refreshSystem]);

  // Initial load
  useEffect(() => {
    void refreshAll();
  }, [refreshAll]);

  // Polling
  useEffect(() => {
    const sysTimer = window.setInterval(() => void refreshSystem(true), 4000);
    return () => window.clearInterval(sysTimer);
  }, [refreshSystem]);

  useEffect(() => {
    const bootTimer = window.setInterval(() => void refreshBootstrap(true), 12000);
    return () => window.clearInterval(bootTimer);
  }, [refreshBootstrap]);

  // Keyboard shortcut: Cmd/Ctrl+Q to quit
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === "q") {
        event.preventDefault();
        void handleQuit();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleQuit]);

  // Sidebar collapse state
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    return localStorage.getItem("vloop-sidebar-collapsed") === "true";
  });

  const toggleSidebar = useCallback(() => {
    setSidebarCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem("vloop-sidebar-collapsed", String(next));
      return next;
    });
  }, []);

  // Mutations that optimistically update local state
  const handleProviderSaved = useCallback((provider: ProviderConfig) => {
    setBootstrap((current) => ({
      ...current,
      providers: sortProviders(upsertById(current.providers, provider)),
    }));
  }, []);

  const handleProviderDeleted = useCallback((providerId: string) => {
    setBootstrap((current) => ({
      ...current,
      providers: current.providers.filter((p) => p.id !== providerId),
    }));
  }, []);

  const handleAgentSaved = useCallback((agent: AgentConfig) => {
    setBootstrap((current) => ({
      ...current,
      agents: sortAgents(upsertById(current.agents, agent)),
    }));
  }, []);

  const handleAgentDeleted = useCallback((agentId: string) => {
    setBootstrap((current) => ({
      ...current,
      agents: current.agents.filter((a) => a.id !== agentId),
    }));
  }, []);

  const handleInvocationSaved = useCallback((invocation: InvocationRecord) => {
    setBootstrap((current) => ({
      ...current,
      invocations: sortInvocations(upsertById(current.invocations, invocation)).slice(0, 50),
    }));
  }, []);

  return {
    bootstrap,
    system,
    bootstrapLoading,
    systemLoading,
    bootstrapError,
    systemError,
    lastRefreshAt,
    shuttingDown,
    shutdownError,
    theme,
    setTheme,
    sidebarCollapsed,
    toggleSidebar,
    handleQuit,
    refreshAll,
    handleProviderSaved,
    handleProviderDeleted,
    handleAgentSaved,
    handleAgentDeleted,
    handleInvocationSaved,
  };
}

function upsertById<T extends { id: string }>(current: T[], nextItem: T): T[] {
  const next = current.filter((item) => item.id !== nextItem.id);
  next.unshift(nextItem);
  return next;
}
