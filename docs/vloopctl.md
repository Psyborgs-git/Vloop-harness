# `vloopctl` — Control Utility Specification

`vloopctl` is the operator and support surface for the local VLoop installation. It is the one binary that installers, launchers, support scripts, and advanced users rely on for lifecycle management and diagnostics.

---

## 1. Purpose

`vloopctl` provides a stable command set for:

- service installation and removal;
- daemon start/stop/restart/status;
- UI opening;
- log access;
- environment diagnostics (`doctor`).

It must be safe to use from:

- native installers;
- app launchers and shortcuts;
- support tooling;
- terminal usage when needed.

---

## 2. Core commands

| Command | Purpose |
|---|---|
| `install-service` | Register OS-native service/agent/task for `vloopd`. |
| `uninstall-service` | Remove service registration cleanly. |
| `start` | Start or request start of `vloopd`. |
| `stop` | Stop `vloopd` cleanly. |
| `restart` | Restart `vloopd` and its CP child process. |
| `status` | Show daemon health, CP registration, dependency readiness, and key runtime status. |
| `open-ui` | Ask the CP to open or focus the main UI window. |
| `logs` | Print or export recent logs and failure context. |
| `doctor` | Run readiness checks and return actionable diagnostics. |

---

## 3. Output model

`vloopctl` should support:

- human-readable default output;
- structured JSON output for automation;
- clear exit codes;
- short, actionable error messages.

### Suggested exit-code categories

| Exit code class | Meaning |
|---|---|
| `0` | success |
| `1` | general failure |
| `2` | dependency or environment issue |
| `3` | service-control issue |
| `4` | daemon reachable but degraded |

---

## 4. `doctor` checks

`doctor` should validate at least:

- service registration exists and is healthy;
- `vloopd` process is running or can start;
- local IPC endpoint is reachable;
- Python CP is registered;
- Docker availability and readiness;
- runtime directories and permissions;
- database resource readiness;
- launcher/UI open path;
- version compatibility between kernel, CP, and frontend bundle.

The output must tell a non-technical user what to do next.

---

## 5. Platform behavior

| OS | Control path |
|---|---|
| macOS | `launchctl`-backed user service control. |
| Windows | Windows Service control, with scheduled-task fallback when necessary. |
| Linux | `systemctl --user` control. |

`vloopctl` is the abstraction over those OS differences.

---

## 6. Security rules

- `vloopctl` must not print raw secret values.
- diagnostics must redact credentials and capability tokens.
- destructive operations should be explicit and auditable.
- `open-ui` should only target the local user session.

---

## 7. Build requirements

`vloopctl` is considered complete when:

- installers can call it reliably;
- users can recover the product using `status` and `doctor`;
- logs and health are understandable without reading source code;
- service operations behave consistently across all target OSes.
