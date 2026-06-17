# AgentLoop

## Overview
The primary execution driver inside the Python Control Plane.

## Responsibilities
- Receives a high-level objective and compiles it into a discrete Directed Acyclic Graph (DAG) using `WorkflowManager`.
- Steps through the DAG, invoking `CodeGenerator` and `PolicyGenerator` as needed.
- Interacts directly with the `IExecutionManager` port to dispatch jobs.

## Interactions
- **WorkflowManager**: Stores node dependencies.
- **DSPy Modules**: Requests code/policy generation.
- **Execution Adapters**: Dispatches the sandboxed jobs.
