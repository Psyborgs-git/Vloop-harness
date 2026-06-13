# ADR 002: Rust Kernel Isolation

## Status
Accepted

## Context
The cognitive engine (Python) executes non-deterministic, AI-generated code and interacts with external MCPs. It must be treated as an untrusted guest to ensure system security.

## Decision
The Rust kernel acts as a pure native hypervisor, owning only critical system-level operations: sandbox provisioning and process management, secure vault management with variable injection into processes at startup, network fencing, gRPC/QUIC transport, and SQLite-backed terminal logging. All AI context, payload introspection, and application-level configuration logic are explicitly offloaded to the backend (Python). The Python app merely requests execution, provides necessary parameters, and streams the output via gRPC. 

## Consequences
- **Pros:** Hard boundary between the cognitive layer and execution layer. The Rust kernel can impose immutable constraints (e.g., Docker `--network none`) that a compromised Python engine cannot bypass. Reduces complexity in the kernel by removing AI awareness and application configs.
- **Cons:** Requires a robust IPC layer (gRPC) and diligent synchronization of state between the Python orchestrator and the execution layer.
