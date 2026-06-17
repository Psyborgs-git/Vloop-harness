# Python Control Plane

## Overview
The stateless agent orchestrator. Implements a strict Hexagonal Architecture and relies on DSPy and LiteLLM.

## Responsibilities
- Compiles user objectives into DAG workflows.
- Generates code and security policies using DSPy.
- Enforces token budgets and caches LLM calls via the `LLMGateway`.
- Runs a local FastAPI proxy to intercept LLM calls from sandboxed tools.

## Interactions
- **Rust Microkernel**: Receives tasks via gRPC.
- **External LLM**: Makes completion requests.
- **Execution Sandboxes**: Dispatches jobs via Hexagonal Adapters.
