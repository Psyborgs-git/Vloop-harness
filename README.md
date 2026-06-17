# VLoop: Product Requirements Document & System Architecture

**Version:** 1.0 (Finalized Baseline)  
**Target Platforms:** Windows, macOS, Linux  
**Core Paradigm:** Hexagonal Architecture, Rust Microkernel, Isolated DSPy Execution Sandboxes.

## 1. Executive Summary

VLoop is a cross-platform, local-first orchestration engine for autonomous agents. It leverages a Rust microkernel to supervise an abstracted Python (DSPy) control plane. Agents never run on the host OS; they execute inside strictly isolated, ephemeral sandboxes (local Docker or remote Kubernetes). The system enforces hard resource limits, dynamic network policies, and audit-logged LLM interactions.

## 2. Core Architecture (The Stack)

### 2.1 Tauri UI (The Mission Control)

* **Role:** IPC interface, visualizer, and secret manager.
* **Vault:** Stores external API keys (OpenAI, AWS, etc.) securely using OS-native credential managers (via Tauri plugins). Keys are passed to the backend strictly at runtime per-session.
* **HITL (Human-in-the-Loop):** UI pauses and prompts the user to approve high-risk sandbox executions or token limit overrides.
* **Auditing:** Streams and displays the chronological audit log of all LLM calls, costs, and sandbox actions.

### 2.2 Rust Microkernel (The Hypervisor)

* **Role:** The absolute source of truth for host state.
* **Process Supervisor:** Uses `std::process::Command` to boot, monitor, and gracefully restart the Python Control Plane natively on Windows/Mac/Linux. No `systemd` dependencies.
* **Hardware Probing:** Dynamically calculates safe memory limits for local execution: `Available_RAM = Total_RAM - (OS_Baseline + Rust/Tauri_Overhead + 1GB_Safety_Buffer)`.
* **Config Injector:** Writes active configuration states to `~/.vloop/rust/active.toml` before booting Python.

### 2.3 Python Control Plane (The Brain - Hexagonal)

* **Role:** Stateless agent orchestration. Compiles tasks, evaluates execution, and optimizes DSPy prompt weights.
* **LiteLLM Integration:** Uses LiteLLM for dynamic model routing. Configured per-session (not globally) using runtime keys injected from Tauri.
* **Cost/Token Gateway:** Implements a strict middleware tracking tokens. If an agent loop exceeds the configured threshold, the Control Plane kills the loop.
* **Dynamic Policy Generator:** DSPy assesses the task before execution and generates a strict JSON policy (e.g., `{"network": false, "volume_mount": false, "hitl_required": true}`).

### 2.4 Abstract Execution Sandbox (The Muscle)

* **Role:** Ephemeral task execution.
* **Implementation:** Hexagonal `IExecutionManager`.
* **Adapter A (Local):** Raw Docker daemon API. Spins up individual containers for local tasks, enforcing the Rust-calculated memory caps.
* **Adapter B (Managed K8s):** Uses Kubeconfigs to dispatch Kubernetes Jobs to EKS, GKE, AKS, or K3s.

## 3. The Hexagonal Port/Adapter Interfaces

To prevent vendor lock-in, the Python CP binds to abstract interfaces.

### 3.1 State & Memory Adapters

* **`IVectorStore`:**
  * **Default (Zero-Dep):** Local ChromaDB/DuckDB.
  * **Configurable:** Postgres + pgvector.

* **`IRelationalDB`:**
  * **Default (Zero-Dep):** SQLite.
  * **Configurable:** PostgreSQL.

* **`IQueue`:**
  * **Default (Zero-Dep):** In-memory / SQLite-backed queue.
  * **Configurable:** Redis.

### 3.2 Execution Adapters (`IExecutionManager`)

* `dispatch_job(spec, policy)`: Takes a generated code artifact and a DSPy-generated security policy.
* `stream_logs(job_id)`: Pipes stdout/stderr back to the evaluator.
* `teardown(job_id)`: Nukes the container/pod.

## 4. File System Boundaries (`~/.vloop/`)

Strict adherence to this structure prevents state corruption across OS environments.

## 5. Execution Lifecycles

### 5.1 Cold Boot Sequence

1. User launches Tauri app.
2. Tauri sends `init` IPC to Rust.
3. Rust probes OS memory, calculates local sandbox limits.
4. Rust reads UI configs (e.g., "Use SQLite, Use Local Docker").
5. Rust generates `active.toml` and spawns the Python process (`std::process`).
6. Python parses config, binds to the specific Adapters, starts LiteLLM router.
7. Python opens a WebSocket/gRPC channel back to Rust. System Ready.

### 5.2 Agent Task Execution (The DSPy Loop)

1. Ingestion: Tauri passes goal: "Scrape X, format as CSV". Injects temporary OpenAI key.
2. Compilation: Python DSPy uses LiteLLM to generate code and a security policy (`network: true`, `hitl: false`).
3. Dispatch: Python calls `IExecutionManager.dispatch_job()`.
   * **If Local:** Hits local Docker API, mounts code, sets RAM limit.
   * **If Remote:** Hits K8s API, generates Job spec.
4. Execution & Teardown: Container runs, outputs to stdout, exits. Adapter captures exit code and destroys the container immediately.
5. Evaluation: DSPy reads stdout. If exit code `1` (fail), DSPy uses LiteLLM to analyze stderr, updates its weights, and retries (until Token/Iteration Cap is hit).
6. Storage: Successful output written to `~/.vloop/control-plane/artifacts/`.

## 6. End-to-End Build Plan (Phases)

### Phase 1: The Microkernel (Rust)

* **Goal:** Establish the hypervisor and filesystem.
* **Tasks:**
  * Initialize Tauri project.
  * Build the `~/.vloop` directory generator.
  * Implement the native OS process supervisor (`std::process::Command`) to boot and monitor a dummy Python script.
  * Implement the hardware memory probe logic.

### Phase 2: The Hexagonal Control Plane (Python)

* **Goal:** Establish the stateless backend.
* **Tasks:**
  * Setup Python daemon (FastAPI/gRPC).
  * Build the Port/Adapter interfaces for `IVectorStore` and `IRelationalDB`.
  * Implement the zero-dependency defaults (SQLite/Chroma).
  * Implement configuration parsing from `~/.vloop/rust/active.toml`.

### Phase 3: Execution Sandboxes

* **Goal:** Abstract local and remote execution.
* **Tasks:**
  * Build `IExecutionManager`.
  * Implement `LocalDockerAdapter` (using Python Docker SDK).
  * Implement `RemoteK8sAdapter` (using Python Kubernetes SDK).
  * Ensure strict cleanup (teardown on fail/success).

### Phase 4: DSPy Agent Integration

* **Goal:** The brain.
* **Tasks:**
  * Integrate DSPy and LiteLLM.
  * Build the token-tracking middleware and hard-cap cutoff logic.
  * Build the dynamic policy generator (prompting the LLM to output a JSON security spec for the tool it just wrote).
  * Connect the DSPy output loop to `IExecutionManager`.

### Phase 5: UI & Security Polish

* **Goal:** User experience and safety.
* **Tasks:**
  * Build Tauri vault integration for API keys.
  * Build the HITL interception UI (Prompts requiring user "Approve" click).
  * Build the real-time audit log viewer.