### Phase 1: Transport Layer & OS Compatibility (gRPC over QUIC / UDP)

To achieve low-latency streaming without TCP head-of-line blocking:

1. **Protocol Stack:** Use `quinn` (a pure-Rust QUIC implementation) to handle the UDP transport layer. Layer your gRPC definitions (via `tonic` or custom protobufs) on top of this HTTP/3 layer.
2. **OS Nuances:** * **Windows:** UDP socket buffer sizes (`SO_RCVBUF`) default to very small values. The Rust kernel must explicitly request larger buffer sizes (e.g., 8MB) via `setsockopt` to prevent dropped terminal packets during massive stdout dumps (like compiling a heavy monorepo).
* **Linux/macOS:** Works out of the box, but requires configuring `ulimit` for file descriptors if handling many concurrent agent sandboxes.


3. **Data Persistence:** The Rust kernel will embed SQLite to log all bidirectional terminal data, independent of the Python engine. SQLite writes are synchronous and durable, ensuring you don't lose session history if Python crashes, however sqlite only stores metadata and real data should be dumped in jsonl files in our ~/.vloop/terminal_logs/{session_id}/ location or similar location configured & used to store massive data logs from our app locally.

### Phase 2: TTY Key Bindings Injection

An LLM agent or a human operator using the dashboard needs to send exact control sequences to interact with CLI tools (like exiting `nano` or killing a process).

1. **Payload Structure:** The gRPC payload for `stdin` must accept an enum: `RawText` or `ControlKey`.
2. **Translation Matrix:** The Python backend intercepts named key bindings from the UI or LLM and maps them to ANSI hex codes before shipping them over QUIC.
* `Ctrl+C` -> `\x03` (SIGINT)
* `Ctrl+D` -> `\x04` (EOF)
* `Ctrl+Z` -> `\x1A` (SIGTSTP)
* `Esc` -> `\x1B`
* `Up Arrow` -> `\x1B[A`


3. **Execution:** The Rust kernel receives `\x03` and pushes it directly into the `bollard` (Docker) or `russh` (SSH) PTY buffer. The guest OS interprets the hex code and halts the active process.

### Phase 3: The Context Cleaner Middleware

LLMs fail catastrophically when fed raw TTY outputs filled with progress bars and color codes. The token count explodes, and attention mechanisms degrade.

Implement a pure Python middleware class that processes the `stdout` stream *before* it enters the LLM's memory window.

1. **ANSI Stripper:** Use a compiled regex to destroy all terminal color and formatting codes.
* `re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')`


2. **Carriage Return Squashing (The Loading Bar Fix):** CLIs (like `npm install`) use `\r` to overwrite the current line to animate progress bars.
* **Rule:** If the middleware detects `\r` without a `\n`, it overwrites the buffer's current line. The LLM only sees the final, settled state of the progress bar, saving thousands of tokens.


3. **Truncation Heuristics:** If a command dumps a 10,000-line stack trace, cut it. Keep the first 50 lines (context) and the last 100 lines (the actual error), replacing the middle with `\n...[8,850 lines truncated]...\n`.

### Phase 4: Autonomous Rust Kernel (Gating & Native UI)

The Rust kernel must act as an immovable object, completely independent of the React/Python layers.

1. **Network Fencing (Whitelisting):**
* The whitelisting logic happens at the container/VM boundary, not the application layer.
* When Rust provisions a Docker sandbox, it drops all external network access (`--network none` equivalent) and explicitly attaches a proxy container or configures iptables/nftables to only resolve and route traffic to the whitelisted domains (e.g., `github.com`, `registry.npmjs.org`).


2. **Configuration Persistence:** * Settings (whitelists, port allocations, policy limits) are stored in the Rust-managed SQLite database. The kernel reads this on boot to enforce rules instantly.
3. **The Failsafe Native UI:**
* Since React and FastAPI might crash or be uninstalled, you cannot rely on them for emergency overrides.
* Compile the Rust kernel with `egui` (an immediate mode GUI for Rust) or a minimal dedicated native Tauri window.
* **Trigger:** Running the kernel executable with a flag (e.g., `vloop-kernel --ui`) spawns a native OS window (Windows/Mac/Linux) built purely in Rust.
* **Capabilities:** This window binds directly to the SQLite DB to edit whitelists, force-kill rogue sandboxes, and read the persisted terminal logs without any web technologies in the middle.


### Phase 5: The Documentation Ledger (`docs/`)

If you are building a polyglot system (Rust, Python, React) that manages isolated execution environments, undocumented code is dead code. The documentation must act as the absolute source of truth for system boundaries, IPC contracts, and security policies.

Structure your `docs/` directory strictly around the "What, Why, and How."

#### 1. The "Why" - Architectural Decision Records (`docs/ADRs/`)

Never rely on tribal knowledge for critical engineering choices. Document *why* you built it this way so future maintainers (or your future self) don't try to "optimize" it by reverting to HTTP/TCP.

* **`001-quic-over-tcp.md`**: Explains the necessity of UDP/QUIC for the PTY transport layer to avoid head-of-line blocking during massive stdout dumps.
* **`002-rust-kernel-isolation.md`**: Details why the Python cognitive engine is treated as an untrusted guest and why the Rust kernel owns the SQLite DB and network fencing.
* **`003-ansi-stripping-middleware.md`**: Documents the LLM token-saving rationale for squashing `\r` and stripping hex codes before context injection.

#### 2. The "What" - System Architecture (`docs/architecture/`)

High-level structural definitions.

* **`system-context.md`**: The macro view. Defines the three planes: Userland (React), Cognitive (Python/DSPy), and Execution (Rust/Docker/SSH). Include the updated visual architecture here.
* **`state-machine.md`**: Defines the lifecycle of a sandbox (Provision -> Bind PTY -> Execute -> Teardown -> Persist Logs).
* **`security-model.md`**: Explicitly outlines the threat model. States what the Python app is allowed to do (e.g., request execution) and what it cannot do (e.g., bypass the network proxy).

#### 3. The "How" - APIs & IPC Contracts (`docs/api/`)

This is the most critical section. Since Rust and Python communicate via gRPC/QUIC, the schemas must be aggressively documented.

* **`grpc-contracts.md`**: The definitive guide to the Protobuf definitions. Must include the exact payload structures for `stdin` (text vs. control keys) and `stdout`/`stderr` streaming.
* **`uds-routing.md`**: Explains how the Unix Domain Sockets are mapped to specific sandbox UUIDs.
* **`telemetry-schema.md`**: Documents the exact JSON schema emitted by the Rust telemetry collector (token usage, latency, exit codes) back to the Python orchestrator.

#### 4. System Configuration (`docs/config/`)

Detail every knob and dial the kernel exposes.

* **`policy-engine.md`**: A comprehensive guide to `policy.json`. Explain the schema for defining blacklisted commands, resource quotas (CPU/RAM limits per sandbox), and timeout thresholds.
* **`network-whitelisting.md`**: Step-by-step instructions on how the Rust kernel translates user-defined domain whitelists into isolated Docker network proxies or `iptables` rules.
* **`kernel-settings.md`**: Documents the OS-level tuning required, specifically the `SO_RCVBUF` adjustments for UDP on Windows and `ulimit` configurations for Linux.

#### 5. Developer & Operational Usage (`docs/usage/`)

How to actually run, test, and break the system.

* **`local-dev.md`**: The bootstrap guide. How to spin up the Rust kernel, the Python FastAPI server, and the Vite frontend simultaneously.
* **`failsafe-ui.md`**: Instructions for launching the native Rust GUI (`vloop-kernel --ui`). Details how to use it to modify the SQLite configs or kill rogue sandboxes when the web layers crash.
* **`agent-integration.md`**: The guide for writing tools/MCPs. Shows exactly how Hermes or OpenClaw should format their JSON outputs to trigger the `RemoteShell` tool and correctly parse the stripped stdout response.