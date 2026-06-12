# The Failsafe UI

The Rust Kernel is the system's immovable object. If the React frontend or the Python FASTAPI server crashes, you can still manage the system.

## Launching the Native GUI
Run the kernel executable with the `--ui` flag to spawn the `egui` failsafe window:

```bash
cargo run -- --ui
```
or 
```bash
./vloop-harness --ui
```

## Capabilities
This window binds directly to the underlying SQLite database and PTY orchestrator. You can:
* View all active sandboxes.
* Edit network whitelists manually.
* Force-kill rogue sandboxes (e.g., if an LLM agent creates an infinite loop and Python crashes).
* Read persisted terminal logs.
