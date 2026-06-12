# Telemetry Schema

The Rust Kernel emits telemetry data back to the Python orchestrator for billing, monitoring, and debugging.

## JSON Schema

```json
{
  "session_id": "uuid-v4",
  "sandbox_type": "docker",
  "duration_ms": 14500,
  "bytes_rx": 1024,
  "bytes_tx": 5000000,
  "exit_code": 0,
  "resource_usage": {
    "peak_cpu_percent": 85.5,
    "peak_ram_mb": 512
  }
}
```

This telemetry is written to SQLite by the Rust kernel and exposed to Python via a dedicated API endpoint.
