# Python Control Plane (The Brain)

The Python Control Plane serves as the cognitive orchestrator for VLoop. Designed using a Hexagonal Architecture, it is a stateless gRPC daemon supervised directly by the Rust microkernel.

## Architecture

The Control Plane lives in the `control-plane/` directory and relies on `uv` for ultra-fast dependency management and environment isolation.

### 1. gRPC Interface (`proto/system.proto`)
The system communicates with the Rust microkernel via gRPC. 
* **Endpoints:**
  * `HealthCheck`: Confirms the Python daemon is running.
  * `ReloadConfig`: Tells Python to re-read `~/.vloop/rust/active.toml`.
  * `DispatchTask`: Accepts an objective string from the UI/Rust and initiates the Agent Loop.

### 2. Hexagonal Ports & Adapters (`core/ports.py`)
To prevent vendor lock-in, the core logic binds to interfaces:
* **`IVectorStore`:** Manages agent memory. Currently implemented via `DummyVectorStoreAdapter`, but designed for ChromaDB/pgvector.
* **`IRelationalDB`:** Manages structured data and audit trails. Implemented via `SQLiteAdapter`.
* **`IExecutionManager`:** Abstracts sandbox execution (see `sandboxes.md`).

### 3. DSPy Agent Integration (`core/agent.py` & `core/dspy_modules.py`)
The orchestrator avoids raw prompting in favor of structural DSPy signatures:
1. **`CodeGenerator`:** Takes an objective (e.g., "Scrape HackerNews") and outputs a self-contained Python script.
2. **`PolicyGenerator`:** Evaluates the generated script and outputs a strict JSON security policy (e.g., restricting network access if unnecessary).
3. **`AgentLoop`:** Dispatches the code to the sandbox, reads the stdout/stderr logs, and if it fails, iterates with the feedback up to a `max_iterations` limit.

### 4. Cost/Token Gateway (`core/gateway.py`)
Because VLoop utilizes LLMs (via `litellm`), it includes a strict token-tracking middleware. 
* **Mechanism:** Wraps `litellm.completion`.
* **Enforcement:** If `total_tokens_used` exceeds `max_tokens` (default 50,000), a `TokenLimitExceeded` exception is thrown, immediately halting the agent loop to prevent runaway costs.
