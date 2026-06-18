# React Frontend Specification

The React frontend is the user-facing application shell for VLoop. It is served by the Python Control Plane and communicates only with CP HTTP/WebSocket APIs.

---

## 1. Responsibilities

The frontend should:

- present application state clearly to a non-technical user;
- create and monitor workflows;
- show logs, progress, approvals, artifacts, and service status;
- expose settings and support surfaces;
- never depend on native/Tauri-specific APIs.

## 2. Runtime boundary

The frontend talks to:

- CP HTTP endpoints for commands and state fetches;
- CP WebSocket streams for real-time updates.

It does **not**:

- talk directly to `vloopd`;
- call Docker, Kubernetes, or filesystem APIs;
- depend on OS-specific browser bridges beyond the CP-owned window runtime.

---

## 3. Application areas

| Area | Purpose |
|---|---|
| Home / dashboard | overall system health and recent workflows |
| Workflow view | step graph, logs, resource status, artifacts |
| Approvals | human-in-the-loop checkpoints |
| Settings | user preferences and product configuration UX |
| Secrets UX | managed vault flows through CP + kernel |
| Support / diagnostics | health, logs, doctor output, version info |

---

## 4. Event model

The frontend should consume real-time events for:

- workflow progress;
- workload status;
- log lines;
- approvals requested/resolved;
- dependency degradation;
- service and CP health changes.

---

## 5. UX rules

- first-run experience must guide the user through readiness states;
- degraded states should be understandable;
- long-running operations should always show progress;
- workflow detail should separate user intent from infrastructure detail without hiding important failure information;
- the UI should remain usable even while backend work continues.

---

## 6. Technical shape

Recommended minimal structure:

- app shell + routing;
- API client under `src/src/lib/`;
- reusable resource/event hooks;
- clear separation between presentation components and API/event state.

---

## 7. Validation requirements

The frontend is complete when it can:

- load from the CP-served bundle;
- display kernel and CP health;
- create a workflow through the CP;
- show streaming logs and state updates;
- open support surfaces without any native runtime dependencies.
