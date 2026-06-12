# UDS Routing

Unix Domain Sockets (UDS) are used internally on Linux/macOS to bridge the Rust gRPC server and individual local PTY instances when they are spawned as isolated subprocesses outside of Docker. 

## Mechanism
When a `Local` sandbox is provisioned:
1. The Rust kernel spawns a background worker attached to the PTY.
2. A unique UDS is created at `/tmp/vloop_sandbox_{session_id}.sock`.
3. The main gRPC router streams data to and from this UDS, abstracting the multi-process architecture away from the Python client.

*Note: On Windows, named pipes (`\\.\pipe\vloop_sandbox_{session_id}`) are used instead of UDS.*
