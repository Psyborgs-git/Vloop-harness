# VLoop Getting Started Guide

Welcome to VLoop! This guide will help you build and run the orchestration engine locally.

## Prerequisites

Ensure you have the following installed:
1. **Rust:** `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.dev | sh`
2. **Node.js (v18+):** Required for the Vite/React frontend.
3. **uv (Python Package Manager):** `curl -LsSf https://astral.sh/uv/install.sh | sh`
4. **Python (3.11+):** Needed by `uv` for the control plane.
5. **Docker:** Required for the local execution sandbox (`LocalDockerAdapter`).

## Installation & Build

1. **Clone the repository:**
   ```bash
   git clone <your-repo-url>
   cd VLoop-harness
   ```

2. **Initialize Frontend Dependencies:**
   ```bash
   cd src
   npm install
   cd ..
   ```

3. **Initialize Control Plane Dependencies:**
   ```bash
   cd control-plane
   uv sync
   cd ..
   ```

## Running the Application

To run the full stack in development mode (which hot-reloads the React UI and boots the Rust microkernel and Python gRPC server automatically):

```bash
cd src-tauri
cargo tauri dev
```

*(Note: Ensure Docker is running in the background so the Python Control Plane can successfully dispatch sandboxed jobs.)*

## Architecture Overview

If you want to understand how the system works under the hood, read the documentation files:
* [Rust Microkernel](./microkernel.md)
* [Python Control Plane](./control-plane.md)
* [Execution Sandboxes](./sandboxes.md)
* [Frontend UI](./frontend.md)
