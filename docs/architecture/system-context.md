# System Architecture Context

## The Three Planes

1. **Userland (React / Tauri Frontend)**
   The visual interface for human operators. Communicates primarily via standard Tauri IPC and WebSockets for real-time updates.

2. **Cognitive Plane (Python / DSPy)**
   The intelligence engine. Handles LLM orchestration, agent workflows, tool calling, and MCP integrations. Communicates with the Rust execution layer via QUIC/gRPC.

3. **Execution Plane (Rust / Docker / SSH)**
   The immovable object. The Rust kernel provisions and manages isolated sandboxes. It enforces network fencing, handles raw PTY input/output, and persists all metadata to SQLite.

## Boundary Interaction
* The Cognitive Plane requests sandboxes and sends `stdin` via gRPC.
* The Execution Plane executes commands and streams `stdout`/`stderr` back via gRPC.
* The Cognitive Plane cleans the stream via `ContextCleaner` before feeding it to the LLM.
