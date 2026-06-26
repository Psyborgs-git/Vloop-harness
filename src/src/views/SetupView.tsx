import { useCallback, useEffect, useState } from "react";
import type { DependencySnapshot, SystemSnapshot } from "../lib/api";
import { getBootstrap } from "../lib/api";
import {
  EmptyState,
  InlineNotice,
  PageHeader,
  Panel,
  StatusBadge,
} from "../components/ui";

interface SetupViewProps {
  system: SystemSnapshot | null;
  systemError: string | null;
}

/** Human-friendly labels for protobuf dependency state enum strings. */
const STATE_LABELS: Record<string, string> = {
  DEPENDENCY_STATE_READY: "Ready",
  DEPENDENCY_STATE_MISSING: "Missing",
  DEPENDENCY_STATE_INSTALLED_BUT_NOT_RUNNING: "Installed (not running)",
  DEPENDENCY_STATE_VERSION_MISMATCH: "Version mismatch",
  DEPENDENCY_STATE_DEGRADED: "Degraded",
  DEPENDENCY_STATE_DISABLED: "Disabled",
  DEPENDENCY_STATE_UNSPECIFIED: "Unknown",
};

/** Map dependency state to a StatusBadge-compatible tone. */
function depTone(state: string): "good" | "warn" | "bad" | "neutral" {
  switch (state) {
    case "DEPENDENCY_STATE_READY":
      return "good";
    case "DEPENDENCY_STATE_DEGRADED":
    case "DEPENDENCY_STATE_INSTALLED_BUT_NOT_RUNNING":
      return "warn";
    case "DEPENDENCY_STATE_MISSING":
    case "DEPENDENCY_STATE_VERSION_MISMATCH":
      return "bad";
    default:
      return "neutral";
  }
}

/** Known install guides the UI can link to. */
const INSTALL_GUIDES: Record<
  string,
  { title: string; body: string; url?: string; automated?: boolean }
> = {
  docker: {
    title: "Docker Engine / Docker Desktop",
    body: "Docker lets VLoop run containerised workloads.  Docker is optional — workloads requiring containers will be unavailable without it, but all other features work fine.  Install Docker Desktop (macOS / Windows) or Docker Engine (Linux).",
    url: "https://docs.docker.com/engine/install/",
    automated: true,
  },
  python_runtime: {
    title: "Python 3",
    body: "Python is required for the VLoop control plane.  Install Python 3.10 or later from python.org, Homebrew, or your system package manager.",
    url: "https://www.python.org/downloads/",
  },
  control_plane_python_packages: {
    title: "Control-plane Python packages",
    body: "Run `vlp init` or `pip install -r requirements.txt` from the control-plane directory to install the required packages.",
  },
  control_plane_entrypoint: {
    title: "Control-plane entrypoint",
    body: "The file `control-plane/main.py` must exist in the VLoop repository root.  Clone the repository or re-run `vlp init`.",
  },
};

/** Render a single dependency card. */
function DependencyCard({
  dep,
}: {
  dep: DependencySnapshot["dependencies"][number];
}) {
  const tone = depTone(dep.state);
  const guide = INSTALL_GUIDES[dep.name];

  return (
    <Panel title={dep.name} key={dep.name}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          marginBottom: 8,
        }}
      >
        <StatusBadge
          status={dep.state}
          label={STATE_LABELS[dep.state] ?? dep.state}
          tone={tone}
        />
        {dep.detectedVersion ? (
          <span className="text-muted" style={{ fontSize: "0.85em" }}>
            {dep.detectedVersion}
          </span>
        ) : null}
      </div>

      <p style={{ margin: "4px 0 8px" }}>{dep.message}</p>

      {dep.remediation ? (
        <InlineNotice tone={tone === "bad" ? "bad" : "warn"} title="How to fix">
          {dep.remediation}
        </InlineNotice>
      ) : null}

      {guide && tone !== "good" ? (
        <div style={{ marginTop: 10 }}>
          <InlineNotice
            tone={guide.automated ? "warn" : "neutral"}
            title={guide.title}
          >
            <p>{guide.body}</p>
            {guide.url ? (
              <a
                href={guide.url}
                target="_blank"
                rel="noopener noreferrer"
                className="link"
              >
                Open install guide →
              </a>
            ) : null}
            {guide.automated ? (
              <p
                style={{
                  marginTop: 8,
                  fontSize: "0.9em",
                  color: "var(--muted)",
                }}
              >
                Docker is optional. All other features (agents, providers, chat,
                AI workflows) work without Docker. Only the Workloads tab
                requires Docker to run containers.
              </p>
            ) : null}
          </InlineNotice>
        </div>
      ) : null}
    </Panel>
  );
}

export function SetupView({ system, systemError }: SetupViewProps) {
  const deps: DependencySnapshot | null = system?.dependencies ?? null;
  const depList = deps?.dependencies ?? [];

  return (
    <div>
      <PageHeader
        title="Setup &amp; Dependencies"
        description="Runtime dependencies and install guides for VLoop."
      />

      {systemError ? (
        <InlineNotice tone="bad" title="System endpoint unavailable">
          {systemError}
        </InlineNotice>
      ) : null}

      {deps?.error ? (
        <InlineNotice tone="warn" title="Dependency check warning">
          {deps.error}
        </InlineNotice>
      ) : null}

      {!system && !systemError ? (
        <EmptyState
          title="Checking system…"
          description="Connecting to the VLoop kernel to fetch dependency status."
        />
      ) : depList.length === 0 ? (
        <EmptyState
          title="No dependency data"
          description="The kernel has not reported any dependency checks yet.  Try refreshing the page."
        />
      ) : (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 16,
            marginTop: 20,
          }}
        >
          {depList.map((dep) => (
            <DependencyCard dep={dep} key={dep.name} />
          ))}
        </div>
      )}
    </div>
  );
}
