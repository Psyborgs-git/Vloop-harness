# Proto Contract Blueprint

This document defines the canonical gRPC surface for VLoop. The proto files are the wire contract between the kernel and the Python Control Plane.

---

## 1. Proto files

| File | Purpose |
|---|---|
| `proto/kernel.proto` | Primary kernel-owned local control and infrastructure API. |
| `proto/control_plane.proto` | Optional transition or callback surfaces when a separate CP-owned RPC surface is needed. |

The main implementation target is a kernel-owned API that the CP consumes.

---

## 2. Design rules

- service names should describe domain ownership clearly;
- request and response messages must be explicit, not generic blobs;
- IDs should be stable and typed by domain;
- streaming should be preferred for logs and events;
- secrets should be referenced by grant/capability, not returned raw;
- long-running operations should expose watch/status methods.

---

## 3. Service groups

| Service | Scope |
|---|---|
| `KernelLifecycle` | registration, health, heartbeats, event watch, shutdown/admin controls |
| `WorkloadControl` | create/start/watch/logs/exec/stop/destroy/list workloads |
| `FilesystemControl` | workspaces, volumes, artifacts, archive extraction, garbage collection |
| `DatabaseControl` | provision, endpoint/grant issuance, backup, restore, destroy, status |
| `NetworkControl` | network creation, exposure, routing, service resolution, policy |
| `SecretControl` | put, grant, revoke, rotate, delete, metadata listing |

---

## 4. Shared message conventions

### identifiers

Use explicit IDs such as:

- `session_id`
- `workflow_id`
- `workload_id`
- `workspace_id`
- `volume_id`
- `database_id`
- `secret_id`
- `grant_id`

### timestamps and status

- prefer machine-readable timestamps;
- use enum-like status values where lifecycle modeling matters;
- keep human-readable messages as secondary fields.

### metadata

Requests should support metadata for:

- request IDs;
- capability tokens;
- tracing correlation;
- UI/user context where relevant.

---

## 5. Key message domains

| Domain | Example fields |
|---|---|
| workload spec | image, command, args, env refs, mounts, ports, resources, policy, timeout |
| workspace spec | name, owner workflow, retention policy, mount rules |
| database spec | engine, version, storage class, backup policy, credentials/grant mode |
| secret grant | secret ref, target type, target ID, injection mode, expiry |
| event record | event type, resource type, resource ID, status, timestamp, payload |

---

## 6. Completion criteria

The proto layer is complete when:

- every subsystem has a clear service boundary;
- long-running operations are observable;
- auth and event streaming are modeled directly;
- the contract can support local-first execution without leaking implementation details into the CP.
