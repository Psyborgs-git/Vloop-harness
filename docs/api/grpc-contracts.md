# gRPC Contracts

The definitive guide to the Protobuf definitions for the Sandbox Service.

## `sandbox.proto`

```protobuf
syntax = "proto3";

package sandbox;

service SandboxService {
  rpc Provision (ProvisionRequest) returns (ProvisionResponse);
  rpc Teardown (TeardownRequest) returns (TeardownResponse);
  rpc TerminalStream (stream TerminalInput) returns (stream TerminalOutput);
}
```

### Payloads

*   `TerminalInput`: Supports `RAW_TEXT` for standard input strings and `CONTROL_KEY` for exact hex payloads (e.g., `\x03` for SIGINT). It also supports `RESIZE` for dynamic window sizing.
*   `TerminalOutput`: Returns chunks of `STDOUT` and `STDERR` as bytes. If the process dies, it returns an `EXIT` payload with the `exit_code`.
