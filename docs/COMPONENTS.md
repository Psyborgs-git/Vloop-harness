# Component Deep-Dive Guide

This document details the primary components of the Vloop Harness, broken down by their architectural layers.

## Layer 0: Orchestrator Kernel (Rust / Tauri)

### `Tauri App (Singleton) & IPC Router`
*   **Purpose:** The main executable and system entry point. It guarantees a single instance lock, handles secure boot, application lifecycle, and routes IPC/gRPC requests.
*   **Dependencies:** Tauri core, Tokio async runtime, `tauri-plugin-single-instance`.
*   **Internal Flow:**
```mermaid
sequenceDiagram
    participant OS as Operating System
    participant Tauri as Tauri Singleton
    participant DB as SQLite DB
    participant ProcMgr as Process Manager
    participant Python as Python Backend

    OS->>Tauri: Launch application
    Tauri->>Tauri: Acquire Lock (Exit if duplicate)
    Tauri->>DB: Ensure core services exist
    Tauri->>ProcMgr: Start autostart processes
    ProcMgr->>Python: Spawn Process & Pipe logs
```
*   **Edge Cases & Error Handling:** If a second instance is launched, it instructs the primary instance to focus its window and gracefully exits. Port collisions or DB locks trigger a fallback UI.

### `Process Manager`
*   **Purpose:** Manages the lifecycle (start, stop, delete, restart) of all configured processes (including the Core Python and Node services). It supports multiple execution environments.
*   **Dependencies:** `std::process::Command`, SQLite.
*   **Internal Flow:**
```mermaid
sequenceDiagram
    participant UI as React UI
    participant ProcMgr as Process Manager
    participant Log as process.log

    UI->>ProcMgr: Request 'Start'
    ProcMgr->>ProcMgr: Resolve Environment (Local/Docker/SSH)
    ProcMgr->>ProcMgr: Spawn Child Process
    ProcMgr->>Log: Redirect Stdout & Stderr continuously
    UI->>ProcMgr: Request Logs via IPC
    ProcMgr-->>UI: Return tail of process.log
```
*   **Edge Cases & Error Handling:** Handles orphaned processes by tracking PIDs in a global mutex map (`ACTIVE_PROCESSES`). Logs are truncated when read to prevent massive payloads.

### `Secure Vault`
*   **Purpose:** Stores sensitive credentials in memory securely so they do not live in Python or React state.
*   **Dependencies:** `std::sync::Mutex`, `HashMap`.
*   **Internal Flow:**
```mermaid
sequenceDiagram
    participant Python as Python Backend
    participant WS as Secure WebSocket
    participant Vault as Vault (Mutex)

    Python->>WS: Request Key (OPENAI_API_KEY)
    WS->>Vault: Acquire Lock
    Vault-->>WS: Return Secret
    WS-->>Python: Return Success Response
```
*   **Edge Cases & Error Handling:** If a requested key is not found, it safely returns an explicit Error to the Python caller instead of crashing.

### `Sandbox Executor`
*   **Purpose:** The native execution layer for terminal and file operations.
*   **Dependencies:** `bollard` (Docker daemon interaction), `ssh2` (Remote environments).
*   **Internal Flow:**
```mermaid
sequenceDiagram
    participant Python as Python Backend
    participant Sandbox as Sandbox Executor
    participant Docker as Docker Daemon

    Python->>Sandbox: Execute 'ls -la' in container 'temp_env'
    Sandbox->>Docker: Exec run
    Docker-->>Sandbox: Return stdout/stderr
    Sandbox-->>Python: Return Execution Result
```
*   **Edge Cases & Error Handling:** Container crashes or SSH timeouts bubble up to Python with descriptive tracebacks for the AI to reason about.

## Layer 1: Cognitive Engine (Python / FastAPI)

### `DSPyEngine`
*   **Purpose:** The central AI brain. It wraps the DSPy language model configuration, offloads sync calls to thread pools to avoid blocking the FastAPI event loop, and handles model fallback routing.
*   **Dependencies:** `dspy`, `harness.engine.model_router`, `harness.engine.dynamic_config`.
*   **Internal Flow:**
```mermaid
sequenceDiagram
    participant Request as User/API
    participant DSPy as DSPy Engine
    participant Router as Model Router
    participant LLM as LLM Provider

    Request->>DSPy: Route and run task
    DSPy->>Router: Get optimal model for capabilities
    Router-->>DSPy: Selected Model (e.g. GPT-4)
    DSPy->>LLM: Inference Request
    LLM-->>DSPy: Generated Response
    DSPy-->>Request: Typed Result
```
*   **Edge Cases & Error Handling:** API rate limits or provider outages trigger the `ModelRouter` to automatically walk the fallback chain (e.g., Anthropic -> OpenAI -> local Ollama).

### `Pipeline Builder & Executor`
*   **Purpose:** Constructs Directed Acyclic Graphs (DAGs) of AI tasks. Supports sequential loops, conditional branches, and parallel map-reduce operations.
*   **Dependencies:** `harness.engine.pipelines.base`.
*   **Internal Flow:**
```mermaid
sequenceDiagram
    participant Code as App Code
    participant Exec as Pipeline Executor
    participant NodeA as Node A
    participant NodeB as Node B

    Code->>Exec: Run Sequential Pipeline
    Exec->>NodeA: Execute
    NodeA-->>Exec: Context Update
    Exec->>NodeB: Execute with Node A Context
    NodeB-->>Exec: Final Result
    Exec-->>Code: Return Output
```
*   **Edge Cases & Error Handling:** Failure in a parallel map branch does not inherently crash the pipeline unless strict reduction is required.

### `Policy Engine`
*   **Purpose:** The security gatekeeper for tool calls. It evaluates commands against a permanent blocklist, a configurable denylist, and a directory-specific allowlist.
*   **Dependencies:** `harness.tools.policy`.
*   **Internal Flow:**
```mermaid
sequenceDiagram
    participant Tool as Terminal Tool
    participant Policy as Policy Engine

    Tool->>Policy: Validate 'rm -rf /'
    Policy->>Policy: Check Blocklist
    Policy-->>Tool: Deny (PermanentBlock)
    Tool->>Policy: Validate 'ls -la'
    Policy->>Policy: Check Allowlist
    Policy-->>Tool: Allow
```
*   **Edge Cases & Error Handling:** Commands hitting the blocklist immediately fail with an `AccessDenied` exception. Ambiguous commands trigger Human-in-the-Loop (HITL) approval.

### `Database Tool & AST Parser`
*   **Purpose:** Safely executes database queries generated by the AI.
*   **Dependencies:** `sqlglot` (for AST parsing), SQLAlchemy 2.0 (asyncio).
*   **Internal Flow:**
```mermaid
sequenceDiagram
    participant AI as AI Agent
    participant DBTool as DB Tool
    participant AST as sqlglot Parser
    participant DB as SQLAlchemy

    AI->>DBTool: Execute 'DROP TABLE users;'
    DBTool->>AST: Parse Query
    AST-->>DBTool: Action Type: DDL
    DBTool-->>AI: Error (Operation Not Permitted)
```
*   **Edge Cases & Error Handling:** AST parsing strictly rejects DDL (`DROP`, `ALTER`). Parsing errors return a syntax error back to the AI for self-correction.

#### Common Flow: Tool Execution & HITL Flow
```mermaid
sequenceDiagram
    participant AI as DSPy Engine
    participant Tool as Tool Registry
    participant Policy as Policy Engine
    participant React as React UI
    participant Kernel as Rust Kernel

    AI->>Tool: Attempt destructive action (e.g., rm file)
    Tool->>Policy: Validate against policy.json
    Policy-->>Tool: Requires HITL
    Tool->>React: Send WebSocket HITL Approval Request
    React-->>Tool: User Approves
    Tool->>Kernel: Send IPC Execute Request
    Kernel-->>Tool: Return Sandbox Output
    Tool-->>AI: Action Completed Successfully
```

## Layer 2: Dynamic Userland (React)

### `WorkspaceArea & Dynamic Iframes`
*   **Purpose:** Renders AI-generated React/HTML views in isolation to prevent Main DOM pollution.
*   **Dependencies:** Vite, React `iframe`.
*   **Internal Flow:**
```mermaid
sequenceDiagram
    participant Core as React Host
    participant Render as DynamicIframe Component
    participant Sand as Sandboxed Iframe

    Core->>Render: Mount new view ID
    Render->>Sand: Inject raw HTML/JS via srcdoc
    Sand-->>Render: postMessage(VLOOP_IFRAME_READY)
    Render->>Sand: Inject initial state
```
*   **Edge Cases & Error Handling:** Infinite loops in generated code only crash the iframe, not the main application. Error boundaries catch standard React rendering errors.

### `App Manifest Installer`
*   **Purpose:** Links backend Python components/pipelines to generated frontend views.
*   **Dependencies:** `harness/data/models.py` (AppManifest schema).
*   **Internal Flow:**
```mermaid
sequenceDiagram
    participant AI as AI Generator
    participant Installer as Manifest Installer
    participant DB as State Store
    participant UI as React UI

    AI->>Installer: Output new Component & View Manifest
    Installer->>Installer: Validate Schema Contract
    Installer->>DB: Save Manifest Record
    Installer-->>UI: Notify new App Available
```
*   **Edge Cases & Error Handling:** Schema validation mismatches between the generated backend payload and the frontend expectation highlight the specific missing keys to the user.