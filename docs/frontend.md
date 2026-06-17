# VLoop Frontend UI (Mission Control)

The frontend is a React + TypeScript application bundled seamlessly within Tauri v2. It acts as the user-facing dashboard for orchestration and secure credential management.

## 1. Architecture
* **Framework:** React + Vite (`src/`).
* **Integration:** Built and statically served by the Tauri Rust backend.

## 2. Secure Vault (`components/Vault.tsx`)
API keys (like `OPENAI_API_KEY`) are highly sensitive.
* **Mechanism:** We utilize `@tauri-apps/plugin-store` to save credentials natively on the OS filesystem (`.vloop-vault.dat`) rather than in browser `localStorage`.
* **Runtime Injection:** The keys are loaded securely at runtime and passed via IPC (Inter-Process Communication) to the backend.

## 3. Audit Log & Agent Orchestration (`components/AuditLog.tsx`)
Users interact with the system by providing natural language objectives.
* **Dispatch:** Objectives are sent to Rust via `invoke('dispatch_task')`.
* **Visibility:** Rust acts as a proxy, forwarding the gRPC request to the Python Control Plane.
* **Real-time Feedback:** As the DSPy Agent Loop iterates, generates code, and evaluates sandboxes, the statuses are streamed back to the React UI for full Human-in-the-Loop visibility.
