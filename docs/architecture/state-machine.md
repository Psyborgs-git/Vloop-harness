# Sandbox Lifecycle State Machine

1. **PROVISIONING**
   - Client requests a sandbox (Docker, SSH, Local).
   - Rust kernel validates request against `policy.json`.
   - Rust provisions resources (e.g., `docker run --network none`).

2. **BOUND**
   - PTY is attached.
   - Bidirectional QUIC/gRPC stream is established.
   - Terminal is ready for `stdin`.

3. **EXECUTING**
   - Commands are actively running.
   - `stdout` and `stderr` are streaming back to the client.
   - Rust kernel monitors resource usage and timeouts.

4. **TEARDOWN**
   - Process exits or is forcefully killed.
   - PTY is closed.
   - Docker container is removed (`--rm`).

5. **PERSISTED**
   - Session metadata is finalized in SQLite.
   - Raw logs remain in `~/.vloop/terminal_logs/{session_id}/log.jsonl`.
