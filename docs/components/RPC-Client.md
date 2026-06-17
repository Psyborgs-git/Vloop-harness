# RPC Client

## Overview
The Tonic-based gRPC client inside the Rust Microkernel.

## Responsibilities
- Establishes a connection to the Python Control Plane (via Unix Domain Sockets on Unix, or TCP on Windows).
- Dispatches `TaskRequest`, `WorkflowStateRequest`, and `RewindRequest` messages.

## Interactions
- **Python CP**: Sends structured Protocol Buffer messages.
