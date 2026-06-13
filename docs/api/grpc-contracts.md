# gRPC Contracts

The definitive guide to the Protobuf definitions for the Sandbox Service.

## `sandbox.proto`

```protobuf
syntax = "proto3";

package sandbox;

service SandboxService {
  rpc Provision (ProvisionRequest) returns (ProvisionResponse);
  rpc Teardown (TeardownRequest) returns (TeardownResponse);
}
```
