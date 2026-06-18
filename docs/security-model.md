# Security Model

This document defines the trust boundaries and security posture for VLoop.

---

## 1. Primary trust boundaries

| Boundary | Description |
|---|---|
| User UI ↔ CP | user-facing commands, approvals, settings, and status |
| CP ↔ Kernel | trusted local control path with explicit auth and capability model |
| Kernel ↔ Runtime backends | Docker now, Kubernetes later |
| Kernel ↔ Secret store | secure secret authority and injection path |
| Workloads ↔ external network | policy-controlled access only |

---

## 2. Security principles

- infrastructure authority belongs to the kernel;
- secrets are granted and injected, not copied around casually;
- generated code never runs on the host directly;
- local IPC is the only trusted CP↔kernel path;
- workloads receive only the minimum capabilities they need;
- logging and diagnostics should redact secrets and sensitive tokens.

---

## 3. Threats to address

- workload breakout or unsafe host-path access;
- secret leakage through environment, logs, or UI;
- unauthorized local process access to IPC;
- stale or replayed capability usage;
- accidental port exposure;
- orphaned privileged resources after crashes.

---

## 4. Required controls

| Area | Control |
|---|---|
| IPC | secure local transport, auth metadata, request IDs, session validation |
| Filesystem | managed paths only, path canonicalization, safe extraction |
| Workloads | explicit policy mapping, resource limits, audited lifecycle |
| Secrets | capability grants, injection modes, rotation, revocation |
| Networking | explicit exposure policy and route tracking |
| Logging | structured logs with redaction |

---

## 5. Audit model

The system should record:

- secret grant issuance and revocation;
- workload creation/start/stop/failure;
- service lifecycle events;
- approval checkpoints and overrides;
- dependency degradation and remediation actions.

---

## 6. Validation requirements

The security model is complete when:

- host execution fallback does not exist;
- secrets stay inside managed grant/injection paths;
- local IPC cannot be used casually by unrelated local processes;
- resource and network exposure is explicit, not accidental.
