# System Architecture Context

## The Three Planes

1. **Userland (React / Tauri Frontend)**
   The visual interface for human operators. Communicates primarily via standard Tauri IPC and WebSockets for real-time updates.

2. **Cognitive Plane (Python / DSPy)**
   The intelligence engine. Handles LLM orchestration, agent workflows, tool calling, and MCP integrations. Communicates with the Rust execution layer via QUIC/gRPC.

3. **Execution Plane (Rust Native Hypervisor / Docker / SSH)**
   The immovable object. The Rust kernel acts as a native hypervisor that provisions and manages isolated sandboxes and processes. It manages the Secure Vault and injects vault variables as environment variables directly into processes upon startup. It enforces network fencing, handles raw PTY input/output via gRPC/QUIC, and persists terminal logs and kernel-level network rules to SQLite. The kernel is completely devoid of AI awareness or application-level configurations, strictly offloading these to the Cognitive Plane.

## Boundary Interaction
* The Cognitive Plane requests sandboxes and sends `stdin` via gRPC.
* The Execution Plane executes commands and streams `stdout`/`stderr` back via gRPC.
* The Cognitive Plane cleans the stream via `ContextCleaner` before feeding it to the LLM.
