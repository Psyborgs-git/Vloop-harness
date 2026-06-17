# Supervisor

## Overview
A Rust component inside the Microkernel responsible for process management.

## Responsibilities
- Spawns the Python Control Plane using `std::process::Command` (e.g., `uv run python main.py`).
- Captures standard output and standard error from the Python process.
- Restarts the process if it crashes unexpectedly.

## Interactions
- **Python CP**: Directly manages its OS-level process lifecycle.
