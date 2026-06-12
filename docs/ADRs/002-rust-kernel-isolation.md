# ADR 002: Rust Kernel Isolation

## Status
Accepted

## Context
The cognitive engine (Python) executes non-deterministic, AI-generated code and interacts with external MCPs. It must be treated as an untrusted guest to ensure system security.

## Decision
The Rust kernel owns all critical system operations: sandbox provisioning, SQLite configuration/state persistence, and network fencing. The Python app merely requests execution and streams the output via gRPC. 

## Consequences
- **Pros:** Hard boundary between the cognitive layer and execution layer. The Rust kernel can impose immutable constraints (e.g., Docker `--network none`) that a compromised Python engine cannot bypass.
- **Cons:** Requires a robust IPC layer (gRPC) and diligent synchronization of configuration state.
