# Local Host OS

## Overview
The native operating system (Windows, macOS, Linux) running the VLoop Application.

## Responsibilities
- Provides file system access for the strict `~/.vloop/` directory boundary.
- Exposes hardware metrics (Total RAM, CPU availability).
- Provides native process execution APIs (`std::process` in Rust).

## Interactions
- **Rust Microkernel**: Queried for hardware limits to safely cap Docker container memory usage.
