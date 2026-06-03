# AI Harness OS - Implementation Plan

## Product Vision
The AI Harness OS is a secure, extensible, AI-driven operating system sandbox running in three distinct layers:
1. **Layer 0: Orchestrator Kernel (Rust/Tauri)**: Manages process lifecycles, health checks, ports, filesystem permissions, API vaults, and execution sandboxes.
2. **Layer 1: Cognitive Engine (FastAPI/Python)**: Uses DSPy/LiteLLM. Base Agent generates configurations, auto-evaluation loops, and dynamically relays HITL requests.
3. **Layer 2: Dynamic Userland (React)**: Dynamic web layer rendering generated code inside iframes, handling user interaction and HITL approvals via Python backend.

## Architectural Guidelines
* **IPC**: Rust and Python communicate via IPC/Secure WebSockets. Rust does NOT talk directly to React. React talks to Python (FastAPI).
* **HITL Flow**: Python (DSPy/Tool) -> Requests permission -> Rust Kernel verifies -> Requires HITL -> Rust sends IPC to Python -> Python relays to React -> User Approves/Rejects -> React sends to Python -> Python sends IPC to Rust.
* **Vault**: Keys and sensitive data are stored in a Rust-managed Secure Vault. DB credentials can be injected at process spawn, but other keys are retrieved by Python at runtime via IPC.
* **Sandboxing**: Rust fully implements the transport layer (Docker via `bollard`, SSH via `ssh2`). React dynamically loads AI-generated UI in sandboxed iframes/webviews.

## Implementation Progress Tracker

### Epic 1: The Micro-Kernel Boot Lifecycle
- [x] **1.1 Secure Boot & Health Checks**: Verify internal tools, DB, and binaries (Python, Node). Scan available network ports dynamically and pass them to backend/frontend.
- [x] **1.2 Native Fallback UI**: Create a standalone HTML/JS Tauri native view independent of React. Display boot logs. Handle port conflicts and allow user to configure before launching React Userland.

### Epic 2: The Permission Gateway & Execution Sandboxes
- [ ] **2.1 Granular Command Allowlist & HITL**: Rust maintains allow/denylist. Benign executes silently. Intrusive triggers HITL via Rust -> Python -> React. Save persistence rules.
- [x] **2.2 Configurable Execution Sandboxes**: Rust manages transport. Use `bollard` for Docker, `ssh2` for SSH. Python requests "execute command X in sandbox Y".

### Epic 3: The Self-Evolving Cognitive Engine (FastAPI + DSPy)
- [x] **3.1 Model Agnostic & Secure Vault**: Rust Secure Vault implementation. Python calls IPC to get LiteLLM keys. DB connections injected securely.
- [x] **3.2 Base Agent & Dynamic Pipeline**: Base agent writes *physical files* for DSPy configs into pipeline directories. Automatic metrics evaluation setup. Hot-reload pipeline paths.
- [x] **3.3 Dual-Vector Learning**: Accept user feedback via API routes. Autonomous self-evaluations. Optimise prompts with DSPy datasets.

### Epic 4: Extensibility & The Dynamic Userland (React)
- [ ] **4.1 Base Routing & Interface**: `/`, `/chats`, `/chats/:id`, `/settings`. Map chat interfaces to DSPy pipelines.
- [x] **4.2 AI-Generated Dynamic UI**: Sandboxed iframe loading of AI-generated components. Securely consume pipeline APIs.
- [x] **4.3 Extension Manifests**: Parse VSCode-style manifests. Bulk HITL approval via Rust -> Python -> React loop. Enforce sandbox permissions at runtime.
