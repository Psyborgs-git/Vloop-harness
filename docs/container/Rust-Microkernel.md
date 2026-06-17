# Rust Microkernel

## Overview
The native hypervisor and supervisor layer of VLoop. Written in Rust for zero-dependency deployment and robust memory safety.

## Responsibilities
- Acts as the absolute source of truth for host state.
- Supervises the Python Control Plane via `std::process`, handling boot, monitoring, and graceful restarts.
- Calculates dynamic hardware memory limits.
- Manages the `~/.vloop/` file system boundary.
- Communicates with the Python layer via gRPC (Tonic).

## Interactions
- **Tauri UI**: Receives IPC commands.
- **Python Control Plane**: Spawns the process and sends gRPC task dispatch/heartbeat messages.
