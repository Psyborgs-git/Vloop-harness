import type { ReactNode } from "react";

export type NoticeTone = "neutral" | "accent" | "good" | "warn" | "bad";

export interface KeyValueItem {
  label: string;
  value: ReactNode;
}

interface PanelProps {
  title?: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}

interface PageHeaderProps {
  title: string;
  description: string;
  actions?: ReactNode;
}

interface EmptyStateProps {
  title: string;
  description: string;
  action?: ReactNode;
}

interface JsonBlockProps {
  value: unknown;
  emptyLabel?: string;
}

interface StatusBadgeProps {
  status?: string | boolean | null;
  label?: string;
  tone?: NoticeTone;
}

interface InlineNoticeProps {
  tone?: NoticeTone;
  title: string;
  children?: ReactNode;
}

export function PageHeader({ title, description, actions }: PageHeaderProps) {
  return (
    <header className="page-header">
      <div className="page-header__content">
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {actions ? <div className="page-header__actions">{actions}</div> : null}
    </header>
  );
}

export function Panel({
  title,
  subtitle,
  actions,
  children,
  className,
}: PanelProps) {
  return (
    <section className={cx("panel", className)}>
      {title || subtitle || actions ? (
        <header className="panel__header">
          <div>
            {title ? <h2 className="panel__title">{title}</h2> : null}
            {subtitle ? <p className="panel__subtitle">{subtitle}</p> : null}
          </div>
          {actions ? <div className="panel__actions">{actions}</div> : null}
        </header>
      ) : null}
      <div className="panel__body">{children}</div>
    </section>
  );
}

export function StatusBadge({ status, label, tone }: StatusBadgeProps) {
  const normalizedTone = tone ?? inferTone(status);
  const text = label ?? statusLabel(status);
  return (
    <span className={cx("badge", `badge--${normalizedTone}`)}>
      <span className="badge__dot" />
      <span>{text}</span>
    </span>
  );
}

export function InlineNotice({
  tone = "neutral",
  title,
  children,
}: InlineNoticeProps) {
  return (
    <div
      className={cx("notice", `notice--${tone}`)}
      role={tone === "bad" ? "alert" : "status"}
    >
      <strong>{title}</strong>
      {children ? <div className="notice__body">{children}</div> : null}
    </div>
  );
}

export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <strong>{title}</strong>
      <p>{description}</p>
      {action ? <div className="empty-state__action">{action}</div> : null}
    </div>
  );
}

export function KeyValueList({ items }: { items: KeyValueItem[] }) {
  return (
    <dl className="key-value-list">
      {items.map((item) => (
        <div className="key-value-list__row" key={item.label}>
          <dt>{item.label}</dt>
          <dd>{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function JsonBlock({
  value,
  emptyLabel = "No structured data.",
}: JsonBlockProps) {
  if (value === null || value === undefined) {
    return <p className="muted-text">{emptyLabel}</p>;
  }

  const text =
    typeof value === "string"
      ? value
      : (JSON.stringify(value, null, 2) ?? emptyLabel);

  return <pre className="code-block">{text}</pre>;
}

export function formatDateTime(
  value: string | number | null | undefined,
): string {
  if (value === null || value === undefined || value === "") {
    return "—";
  }

  const date =
    typeof value === "number" ? new Date(value) : new Date(String(value));
  if (Number.isNaN(date.valueOf())) {
    return String(value);
  }

  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

export function formatRelativeTime(
  value: string | number | null | undefined,
): string {
  if (value === null || value === undefined || value === "") {
    return "—";
  }

  const timestamp =
    typeof value === "number" ? value : new Date(String(value)).valueOf();
  if (Number.isNaN(timestamp)) {
    return String(value);
  }

  const deltaMs = timestamp - Date.now();
  const deltaMinutes = Math.round(deltaMs / 60_000);
  if (Math.abs(deltaMinutes) < 1) {
    return "just now";
  }

  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  if (Math.abs(deltaMinutes) < 60) {
    return formatter.format(deltaMinutes, "minute");
  }

  const deltaHours = Math.round(deltaMinutes / 60);
  if (Math.abs(deltaHours) < 24) {
    return formatter.format(deltaHours, "hour");
  }

  const deltaDays = Math.round(deltaHours / 24);
  return formatter.format(deltaDays, "day");
}

export function formatDuration(
  startedAt: string | number | null | undefined,
  finishedAt?: string | number | null,
): string {
  if (startedAt === null || startedAt === undefined || startedAt === "") {
    return "—";
  }

  const start =
    typeof startedAt === "number" ? startedAt : Date.parse(String(startedAt));
  const end =
    finishedAt === null || finishedAt === undefined || finishedAt === ""
      ? Date.now()
      : typeof finishedAt === "number"
        ? finishedAt
        : Date.parse(String(finishedAt));

  if (Number.isNaN(start) || Number.isNaN(end)) {
    return "—";
  }

  const deltaMs = Math.max(end - start, 0);
  if (deltaMs < 1_000) {
    return `${deltaMs} ms`;
  }
  if (deltaMs < 60_000) {
    return `${(deltaMs / 1_000).toFixed(1)} s`;
  }
  const minutes = Math.floor(deltaMs / 60_000);
  const seconds = Math.round((deltaMs % 60_000) / 1_000);
  return `${minutes}m ${seconds}s`;
}

export function cx(
  ...values: Array<string | false | null | undefined>
): string {
  return values.filter(Boolean).join(" ");
}

function inferTone(status: string | boolean | null | undefined): NoticeTone {
  if (typeof status === "boolean") {
    return status ? "good" : "neutral";
  }

  const value = String(status ?? "")
    .trim()
    .toLowerCase();
  if (
    [
      "registered",
      "ready",
      "ok",
      "succeeded",
      "success",
      "enabled",
      "connected",
      "dependency_state_ready",
    ].includes(value)
  ) {
    return "good";
  }
  if (
    [
      "queued",
      "running",
      "starting",
      "starting_http",
      "serving_http",
      "connecting",
      "reconnecting",
      "pending",
      "unknown",
      "dependency_state_degraded",
      "dependency_state_installed_but_not_running",
    ].includes(value)
  ) {
    return "warn";
  }
  if (
    [
      "failed",
      "error",
      "disconnected",
      "denied",
      "dependency_state_missing",
      "dependency_state_version_mismatch",
    ].includes(value)
  ) {
    return "bad";
  }
  if (["session", "active", "selected", "current"].includes(value)) {
    return "accent";
  }
  return "neutral";
}

function statusLabel(status: string | boolean | null | undefined): string {
  if (typeof status === "boolean") {
    return status ? "Yes" : "No";
  }

  if (!status) {
    return "Unknown";
  }

  return String(status)
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(
      /(^|\s)(\w)/g,
      (_, prefix: string, char: string) => `${prefix}${char.toUpperCase()}`,
    );
}
