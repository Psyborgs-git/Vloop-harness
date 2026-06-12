# Local Development Guide

## Bootstrap

To spin up the full polyglot system locally:

1. **Rust Kernel (Backend + gRPC)**
   ```bash
   cd src-tauri
   cargo run
   ```
   *Note: This will launch Tauri. To run just the kernel with the native UI fallback, use `cargo run -- --ui`.*

2. **Python Engine (FastAPI)**
   ```bash
   uv sync
   make dev-backend
   ```
   *This starts the Python orchestrator on `127.0.0.1:9100` and connects to the Rust gRPC on `127.0.0.1:9102`.*

3. **React Frontend (Vite)**
   ```bash
   make dev-frontend
   ```

You now have the three planes running and communicating.
