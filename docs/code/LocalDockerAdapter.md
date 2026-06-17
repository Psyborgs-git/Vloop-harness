# LocalDockerAdapter

## Overview
Implements `IExecutionManager` using the local Docker Daemon API.

## Responsibilities
- Enforces `mem_limit` calculated by the Rust kernel.
- Disables container networking if dictated by the DSPy Policy (`network_disabled`).
- Automatically utilizes the `runsc` (gVisor) runtime if installed to prevent kernel privilege escalation.
