# Docker / Kubernetes

## Overview
The execution sandboxes where generated code or harness tools (like Aider) are run.

## Responsibilities
- Provide ephemeral, isolated environments for untrusted code.
- Enforce memory caps, network restrictions, and gVisor (`runsc`) MicroVM isolation.

## Interactions
- **VLoop Application (Python CP)**: Receives Job specs and DSPy-generated security policies via the `IExecutionManager` adapters.
