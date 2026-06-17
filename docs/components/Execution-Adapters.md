# Execution Adapters

## Overview
The collection of concrete implementations for the `IExecutionManager` port.

## Responsibilities
- Abstract away the specifics of running sandboxed code. Includes `LocalDockerAdapter`, `RemoteK8sAdapter`, and `AiderAdapter`.
