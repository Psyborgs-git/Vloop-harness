# ADR 001: QUIC Over TCP for Sandbox Transport

## Status
Accepted

## Context
Massive stdout dumps (like compiling a heavy monorepo or running `npm install`) generate significant data rapidly. When running these over standard TCP, we encountered head-of-line blocking. If a single packet was lost, the entire stream stalled until it was retransmitted, causing unacceptable latency for the LLM agents trying to read the terminal output in real-time.

## Decision
We chose to adopt QUIC (via `quinn` in Rust and `aioquic` in Python) as the underlying transport for our gRPC communications between the Python Engine and the Rust Kernel.

## Consequences
- **Pros:** Eliminates TCP head-of-line blocking. Allows parallel, low-latency streaming of bidirectional terminal I/O.
- **Cons:** Added complexity to the networking stack. Requires explicit OS tuning (e.g., `SO_RCVBUF` on Windows) to handle UDP buffer sizes efficiently.
