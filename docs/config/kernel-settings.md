# Kernel Settings & OS Tuning

To achieve low-latency streaming without packet loss, the OS must be tuned.

## Windows: UDP Socket Buffer Sizes
Windows defaults `SO_RCVBUF` to very small values. During massive stdout dumps (like compiling), packets will be dropped. The Rust kernel must explicitly request larger buffer sizes (e.g., 8MB) via `setsockopt`.

## Linux/macOS: File Descriptors
Handling many concurrent QUIC/gRPC streams and PTYs requires a high number of open file descriptors.
Administrators should configure `ulimit`:

```bash
ulimit -n 65535
```

This ensures the kernel can scale to hundreds of simultaneous agent sandboxes.
