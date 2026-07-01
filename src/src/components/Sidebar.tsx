import { useMemo } from "react";
import type { AppView } from "../App";
import type { BootstrapPayload, SystemSnapshot } from "../lib/api";
import { StatusBadge, cx, formatRelativeTime } from "../components/ui";

interface NavItem {
  id: AppView;
  label: string;
  description: string;
  count: number | null;
  icon: string;
  abbr: string;
}

interface SidebarProps {
  activeView: AppView;
  onNavigate: (view: AppView) => void;
  bootstrap: BootstrapPayload;
  system: SystemSnapshot | null;
  systemLoading: boolean;
  lastRefreshAt: number | null;
  collapsed: boolean;
  onToggleCollapse: () => void;
  theme: "light" | "dark" | "auto";
  onSetTheme: (theme: "light" | "dark" | "auto") => void;
  shuttingDown: boolean;
  shutdownError: string | null;
  onQuit: () => void;
}

export function Sidebar({
  activeView,
  onNavigate,
  bootstrap,
  system,
  systemLoading,
  lastRefreshAt,
  collapsed,
  onToggleCollapse,
  theme,
  onSetTheme,
  shuttingDown,
  shutdownError,
  onQuit,
}: SidebarProps) {
  const hasIssues =
    system?.dependencies?.dependencies?.filter(
      (d) =>
        d.state !== "DEPENDENCY_STATE_READY" &&
        d.state !== "DEPENDENCY_STATE_DISABLED",
    ).length ?? null;

  const navItems = useMemo<NavItem[]>(
    () => [
      {
        id: "dashboard",
        label: "Dashboard",
        description: "Overview and next steps",
        count: null,
        icon: "⏿",
        abbr: "DB",
      },
      {
        id: "providers",
        label: "Providers",
        description: "Model backends and secrets",
        count: bootstrap.providers.length,
        icon: "⎔",
        abbr: "PR",
      },
      {
        id: "agents",
        label: "Agents",
        description: "Prompted workflows and schemas",
        count: bootstrap.agents.length,
        icon: "◎",
        abbr: "AG",
      },
      {
        id: "chat",
        label: "Chat",
        description: "Converse with agents",
        count: bootstrap.agents.length,
        icon: "💬",
        abbr: "CH",
      },
      {
        id: "usage",
        label: "Usage",
        description: "Token usage and trace logs",
        count: bootstrap.invocations.length,
        icon: "📊",
        abbr: "US",
      },
      {
        id: "playground",
        label: "Playground",
        description: "Run and inspect invocations",
        count: bootstrap.invocations.length,
        icon: "▶",
        abbr: "PL",
      },
      {
        id: "setup",
        label: "Setup",
        description: "Dependencies and install guides",
        count: hasIssues,
        icon: "⚙",
        abbr: "SU",
      },
      {
        id: "system",
        label: "System",
        description: "Health, session, and events",
        count: system?.eventCount ?? null,
        icon: "📡",
        abbr: "SY",
      },
      {
        id: "settings",
        label: "Settings",
        description: "Database and storage configuration",
        count: null,
        icon: "✎",
        abbr: "ST",
      },
      {
        id: "workloads",
        label: "Workloads",
        description: "Docker containers and previews",
        count: null,
        icon: "⊞",
        abbr: "WL",
      },
      {
        id: "workflows",
        label: "Workflows",
        description: "Build, run, and observe workflows",
        count: null,
        icon: "⧉",
        abbr: "WF",
      },
      {
        id: "approvals",
        label: "Approvals",
        description: "Review and decide pending checkpoints",
        count: null,
        icon: "✔",
        abbr: "AP",
      },
      {
        id: "budgets",
        label: "Budgets",
        description: "Budget usage and rate-limit status",
        count: null,
        icon: "$",
        abbr: "BG",
      },
      {
        id: "checkpoints",
        label: "Checkpoints",
        description: "List checkpoints and roll back a run",
        count: null,
        icon: "⟲",
        abbr: "CP",
      },
      {
        id: "schedule",
        label: "Schedule",
        description: "Create, pause, and resume scheduled tasks",
        count: null,
        icon: "⏰",
        abbr: "SC",
      },
    ],
    [
      bootstrap.agents.length,
      bootstrap.invocations.length,
      bootstrap.providers.length,
      system?.eventCount,
      hasIssues,
    ],
  );

  return (
    <aside className={cx("app-sidebar", collapsed && "app-sidebar--collapsed")}>
      <button
        className="sidebar-toggle"
        type="button"
        onClick={onToggleCollapse}
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
      >
        {collapsed ? "→" : "←"}
      </button>

      {!collapsed ? (
        <>
          <div className="brand-block">
            <div className="brand-mark">VL</div>
            <div>
              <strong>VLoop</strong>
              <p>Python Control Plane shell</p>
            </div>
          </div>

          <nav className="nav-list" aria-label="Primary">
            {navItems.map((item) => (
              <button
                key={item.id}
                type="button"
                className={cx(
                  "nav-item",
                  activeView === item.id && "is-active",
                )}
                onClick={() => onNavigate(item.id)}
              >
                <div>
                  <strong>{item.label}</strong>
                  <span>{item.description}</span>
                </div>
                {item.count !== null ? (
                  <span className="nav-item__count">{item.count}</span>
                ) : null}
              </button>
            ))}
          </nav>
        </>
      ) : (
        <nav className="nav-list nav-list--icons" aria-label="Primary">
          {navItems.map((item) => (
            <button
              key={item.id}
              type="button"
              className={cx(
                "nav-item nav-item--icon",
                activeView === item.id && "is-active",
              )}
              onClick={() => onNavigate(item.id)}
              title={item.label}
            >
              <span className="nav-item__icon">{item.icon}</span>
              {item.count !== null ? (
                <span className="nav-item__count">{item.count}</span>
              ) : null}
            </button>
          ))}
        </nav>
      )}

      <div className="sidebar-footer">
        {!collapsed ? (
          <>
            <StatusBadge
              status={
                system?.health.status ??
                (systemLoading ? "starting" : "unknown")
              }
              label={
                system?.health.status
                  ? undefined
                  : systemLoading
                    ? "Loading"
                    : "Unknown"
              }
            />
            <StatusBadge
              tone={bootstrap.apiAvailable ? "accent" : "neutral"}
              label={
                bootstrap.apiAvailable
                  ? "Config API ready"
                  : "System endpoints only"
              }
            />
            <p>
              {lastRefreshAt
                ? `Refreshed ${formatRelativeTime(lastRefreshAt)}`
                : "Waiting for first refresh"}
            </p>

            <div className="sidebar-theme-toggle">
              <button
                type="button"
                className={cx(theme === "light" && "is-active")}
                onClick={() => onSetTheme("light")}
                title="Light theme"
              >
                ☀
              </button>
              <button
                type="button"
                className={cx(theme === "dark" && "is-active")}
                onClick={() => onSetTheme("dark")}
                title="Dark theme"
              >
                ☾
              </button>
              <span style={{ fontSize: "0.8rem", color: "var(--muted)" }}>
                {theme === "auto"
                  ? "Auto"
                  : theme === "dark"
                    ? "Dark"
                    : "Light"}
              </span>
            </div>

            <div className="sidebar-quit">
              {shutdownError ? (
                <p className="sidebar-quit__error">{shutdownError}</p>
              ) : null}
              <button
                className="button button--danger"
                type="button"
                onClick={onQuit}
                disabled={shuttingDown}
              >
                {shuttingDown ? "Shutting down…" : "Quit VLoop"}
              </button>
            </div>
          </>
        ) : (
          <div className="sidebar-footer--collapsed">
            <button
              type="button"
              className="sidebar-collapsed-theme"
              onClick={() => onSetTheme(theme === "dark" ? "light" : "dark")}
              title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
            >
              {theme === "dark" ? "☀" : "☾"}
            </button>
            <button
              className="button button--danger button--small"
              type="button"
              onClick={onQuit}
              disabled={shuttingDown}
              title={shuttingDown ? "Shutting down…" : "Quit VLoop"}
            >
              {shuttingDown ? "…" : "✕"}
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}
