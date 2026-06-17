# VLoop Rust Microkernel

The VLoop Rust Microkernel serves as the hypervisor and absolute source of truth for the local host state. It is a lightweight, zero-dependency (systemd-free) daemon bundled inside a Tauri v2 application that manages the execution environment and enforces security/resource constraints.

## 1. Filesystem Boundaries (`fs.rs`)

To prevent state corruption across different OS environments, the microkernel strictly enforces filesystem boundaries.

On boot, the kernel creates the following tree in the user's home directory:
```
~/.vloop/
├── rust/
│   └── active.toml         # Boot configuration passed to Python
└── control-plane/
    └── artifacts/          # Safe output directory for sandbox artifacts
```

The `active.toml` file is dynamically generated at boot time based on the host's current state and hardware limitations.

## 2. Hardware Resource Limits (`sys.rs`)

VLoop is designed to run locally. To prevent the sandboxes or the LLM evaluation loops from crashing the host OS (OOM), the microkernel dynamically calculates available RAM:

**Limit Formula:**
`Available_RAM = Total_RAM - (OS_Baseline + Safety_Buffer)`

*   **OS_Baseline:** Hardcoded to ~2GB to ensure the host OS (Windows/Mac/Linux) remains stable.
*   **Safety_Buffer:** An additional 1GB reserved for the Rust microkernel and the Tauri Webview overhead.
*   *Fallback:* If the system is heavily constrained, the sandbox is given a strict 512MB limit.

This `Available_RAM` value is serialized into `active.toml` so the Python control plane can enforce it when spawning local Docker containers.

## 3. Process Supervisor (`supervisor.rs`)

The Python Control Plane runs as a stateless child process supervised directly by Rust.

*   **Boot:** The kernel spawns `python3` (to be bundled or resolved from `$PATH`) using `std::process::Command`.
*   **Monitor:** It captures and streams `stdout` and `stderr` natively.
*   **Resilience:** If the Python control plane exits unexpectedly or crashes due to an unhandled exception, the Rust supervisor catches the exit code and automatically restarts it after a 3-second backoff.
