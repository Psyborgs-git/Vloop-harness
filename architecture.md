# VLoop: Comprehensive Software Architecture

**Version:** 1.0
**Target Platforms:** Windows, macOS, Linux
**Core Paradigm:** Hexagonal Architecture, Rust Microkernel, Isolated DSPy Execution Sandboxes.

This document describes the software architecture of VLoop using the **C4 Model** (Context, Container, Component, Code), leveraging Mermaid diagrams to visualize each level of the system. It strictly reflects the concrete classes, adapters, and modules currently implemented in the codebase.

---

## Level 1: System Context Diagram

The System Context diagram provides a high-level overview of how the VLoop application interacts with its external environment, including users, the local operating system, external LLM providers, and execution sandboxes.

```mermaid
C4Context
title System Context diagram for VLoop

Person(user, "User", "Developer or Operator interacting with VLoop")

System(vloop, "VLoop Application", "Local-first orchestration engine for autonomous agents")

System_Ext(llm, "External LLM APIs", "OpenAI, AWS Bedrock, etc. Provide model completions.")
System_Ext(os, "Local Host OS", "File System, RAM. Used for hardware probing and limits.")
System_Ext(sandbox, "Docker / Kubernetes", "Execution environment for ephemeral, isolated tasks.")

Rel(user, vloop, "Configures and monitors agents using", "Tauri UI")
Rel(vloop, llm, "Requests LLM completions using", "HTTPS/REST")
Rel(vloop, os, "Reads/Writes state and checks resource limits using", "Native OS APIs")
Rel(vloop, sandbox, "Dispatches isolated agent jobs using", "Docker API / K8s API")
```

---

## Level 2: Container Diagram

The Container diagram zooms into the VLoop Application to show its core deployable units. VLoop is separated into a frontend UI, a native Rust microkernel hypervisor, and an isolated Python Control Plane that relies on Hexagonal adapters.

```mermaid
C4Container
title Container diagram for VLoop System

Person(user, "User", "Developer or Operator")

System_Boundary(vloop_boundary, "VLoop Application") {
    Container(ui, "React Frontend", "React / Vite / TypeScript", "Visualizer, HITL interceptor, loaded natively by PyWebView.")
    Container(kernel, "Rust Microkernel", "Rust / Tauri", "Headless Daemon, Hypervisor, Swarm Mesh, Secure Vault, System Tray.")
    Container(cp, "Python Control Plane", "Python, PyWebView, DSPy", "Stateless agent orchestration, UI Renderer, Context RAG, Proxy.")
}

System_Ext(sandbox, "Execution Sandbox", "Docker daemon or Managed K8s", "Ephemeral task execution (e.g. Aider harness)")
System_Ext(llm, "External LLM", "OpenAI, etc.", "Model completions")

Rel(user, ui, "Views logs, configures workflows, and approves actions in")
Rel(ui, kernel, "Sends init IPC, config, and injected runtime keys to", "Tauri IPC")
Rel(kernel, cp, "Spawns and monitors via std::process, communicates via", "gRPC (Tonic)")
Rel(cp, kernel, "Sends status, heartbeats, and audit logs via", "Unix Socket/gRPC")
Rel(cp, llm, "Routes model requests via LiteLLM Gateway to", "HTTPS")
Rel(cp, sandbox, "Dispatches jobs using hexagonal adapter policies to", "Docker SDK / K8s SDK")
```

### Documentation Links
- [Tauri UI](docs/container/Tauri-UI.md)
- [Rust Microkernel](docs/container/Rust-Microkernel.md)
- [Python Control Plane](docs/container/Python-Control-Plane.md)

---

## Level 3: Component Diagram

The Component diagram dives deeper into the Rust Microkernel and the Python Control Plane, accurately mapping the Rust modules (`supervisor`, `sys`, `rpc`, `litefs_sync`, etc.) and the Python modules (`LLMGateway`, `Proxy`, `AgentLoop`, and specific `Adapters`).

```mermaid
C4Component
title Component diagram for VLoop Backends

Container_Boundary(kernel, "Rust Microkernel") {
    Component(supervisor, "Supervisor", "Rust", "Spawns and monitors the Python CP natively using std::process")
    Component(rpc, "RPC Client", "Rust/Tonic", "Communicates with Python CP via gRPC")
    Component(sys, "System API", "Rust", "Probes hardware memory and limits")
    Component(fs, "FS Manager", "Rust", "Manages strict ~/.vloop/ filesystem boundaries")
    Component(context_daemon, "Context Daemon", "Rust", "Manages active LLM context and states")
    Component(litefs_sync, "LiteFS Sync", "Rust", "Synchronizes local SQLite DBs")
    Component(swarm, "Swarm Manager", "Rust", "Orchestrates multi-agent processes")
}

Container_Boundary(cp, "Python Control Plane") {
    Component(agent_loop, "AgentLoop", "Python", "Main execution loop, compiles goals into DAGs")
    Component(workflow_mgr, "WorkflowManager", "Python", "Manages DAG node execution")
    Component(generators, "DSPy Modules", "DSPy", "CodeGenerator and PolicyGenerator")
    Component(proxy, "Local Proxy", "FastAPI", "OpenAI-compatible endpoint that intercepts sandbox LLM calls")
    Component(gateway, "LLMGateway", "Python", "LiteLLM cost/token gateway and Semantic Cache enforcement")
    Component(adapters, "Execution Adapters", "Python", "LocalDockerAdapter, AiderAdapter, RemoteK8sAdapter")
    Component(db_adapters, "State Adapters", "Python", "SQLiteAdapter, DummyVectorStoreAdapter")
}

Rel(supervisor, agent_loop, "Starts process", "std::process")
Rel(rpc, agent_loop, "Dispatches tasks and workflows via", "gRPC")
Rel(sys, fs, "Calculates RAM limits, passes config state")
Rel(agent_loop, workflow_mgr, "Registers and executes DAG nodes")
Rel(agent_loop, generators, "Requests code and security policy generation")
Rel(agent_loop, adapters, "Dispatches jobs (e.g. Aider)")
Rel(adapters, proxy, "Sandboxed tools (Aider) call local LLM proxy instead of real API")
Rel(proxy, gateway, "Proxy routes requests through gateway for token limits")
Rel(workflow_mgr, db_adapters, "Stores state and audit logs")
```

---

## Level 4: Code Diagram (Hexagonal Architecture)

The Code-level diagram highlights the true Hexagonal Architecture (Ports and Adapters) utilized by the Python Control Plane, including specialized adapters like `AiderAdapter` and `DummyVectorStoreAdapter`, and components like `LLMGateway`.

```mermaid
classDiagram
direction BT

%% Ports (Interfaces)
class IExecutionManager {
    <<Interface>>
    +dispatch_job(spec, policy) str
    +stream_logs(job_id) Generator
    +teardown(job_id) None
}

class IRelationalDB {
    <<Interface>>
    +connect() None
    +execute_query(query, params) list
    +close() None
}

class IVectorStore {
    <<Interface>>
    +add_document(collection_name, document_id, text, metadata) None
    +search(collection_name, query, top_k) list
}

%% Adapters
class LocalDockerAdapter {
    -max_memory_bytes : int
    -client : docker.DockerClient
    +dispatch_job(spec, policy) str
    +stream_logs(job_id) Generator
    +teardown(job_id) None
}

class AiderAdapter {
    -host_proxy_url : str
    +dispatch_job(spec, policy) str
}

class RemoteK8sAdapter {
    -namespace : str
    +dispatch_job(spec, policy) str
    +stream_logs(job_id) Generator
    +teardown(job_id) None
}

class SQLiteAdapter {
    -db_path : str
    +connect() None
    +execute_query(query, params) list
    +close() None
}

class DummyVectorStoreAdapter {
    -persist_directory : str
    +add_document(collection_name, document_id, text, metadata) None
    +search(collection_name, query, top_k) list
}

%% Relationships
LocalDockerAdapter ..|> IExecutionManager : implements
AiderAdapter --|> LocalDockerAdapter : inherits
RemoteK8sAdapter ..|> IExecutionManager : implements
SQLiteAdapter ..|> IRelationalDB : implements
DummyVectorStoreAdapter ..|> IVectorStore : implements

%% Core Modules
class LLMGateway {
    -max_tokens: int
    -total_tokens_used: int
    +generate(model, messages, kwargs)
}

class CodeGenerator {
    +forward(objective, feedback)
}

class PolicyGenerator {
    +forward(python_code) dict
}

class AgentLoop {
    +exec_manager : IExecutionManager
    +compile_goal_to_dag(objective) str
    +run(objective, max_iterations) dict
}

class WorkflowManager {
    -db_path : str
    +create_workflow(objective, nodes) str
}

AgentLoop --> IExecutionManager : "depends on (Port)"
AgentLoop --> WorkflowManager : "uses"
AgentLoop --> CodeGenerator : "uses"
AgentLoop --> PolicyGenerator : "uses"
WorkflowManager --> IRelationalDB : "depends on (Port)"
```

### Documentation Links

#### Ports (Interfaces)
- [IExecutionManager](docs/code/IExecutionManager.md)
- [IRelationalDB](docs/code/IRelationalDB.md)
- [IVectorStore](docs/code/IVectorStore.md)

#### Adapters
- [LocalDockerAdapter](docs/code/LocalDockerAdapter.md)
- [AiderAdapter](docs/code/AiderAdapter.md)
- [RemoteK8sAdapter](docs/code/RemoteK8sAdapter.md)
- [SQLiteAdapter](docs/code/SQLiteAdapter.md)
- [DummyVectorStoreAdapter](docs/code/DummyVectorStoreAdapter.md)

#### Core Logic
- [CodeGenerator](docs/code/CodeGenerator.md)
- [PolicyGenerator](docs/code/PolicyGenerator.md)

---

## Operational Workflow Highlights

1. **Boot**: The Tauri UI initiates the Rust microkernel. Rust determines hardware limits (`sys`), sets up `fs`, and spawns the Python Control Plane via `supervisor`. Inter-process communication leverages gRPC (`rpc`).
2. **Task Ingestion**: The CP takes a prompt, leverages DSPy + `LLMGateway` (LiteLLM) to compile it into executable code alongside a generated strict security policy via `PolicyGenerator`.
3. **Sandboxed Execution**: The CP routes the job via the `IExecutionManager` port to either local Docker (or a specialized `AiderAdapter`) or remote K8s. 
4. **Proxy & Limits**: Executing harnesses do not have direct access to external API keys. They point to the `FastAPI Proxy`, which intercepts the calls and routes them through the `LLMGateway` for strict token budget enforcement.
5. **Validation**: The job completes. If it fails, standard error output is captured and routed back to DSPy to refine the code until success or the loop threshold limit is met.
 routed back to DSPy to refine the code until success or the loop threshold limit is met.
b via the `IExecutionManager` port to either local Docker (or a specialized `AiderAdapter`) or remote K8s. 
4. **Proxy & Limits**: Executing harnesses do not have direct access to external API keys. They point to the `FastAPI Proxy`, which intercepts the calls and routes them through the `LLMGateway` for strict token budget enforcement.
5. **Validation**: The job completes. If it fails, standard error output is captured and routed back to DSPy to refine the code until success or the loop threshold limit is met.
