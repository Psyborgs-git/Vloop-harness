# Network Manager Specification

The network manager is the kernel subsystem that turns workload networking intent into safe local routing, port allocation, preview URLs, and future distributed network behavior.

---

## 1. Responsibilities

- create and manage local execution networks;
- allocate and track host ports;
- expose or deny workload connectivity according to policy;
- provide service discovery metadata to the CP;
- generate preview URLs for user-visible services;
- support future distributed routing expansion.

---

## 2. Core concepts

| Concept | Meaning |
|---|---|
| network | logical connectivity boundary for one or more workloads |
| service | named endpoint exposed by a workload |
| route | mapping from a local host address/port to a managed service |
| policy | allowed ingress/egress behavior for a workload |
| lease | reserved port or route allocation |

---

## 3. Local runtime model

For local Docker-backed execution, the manager should:

- create or reuse managed Docker networks;
- attach workloads according to policy;
- allocate ports predictably;
- publish discovered service metadata to the CP;
- reclaim leases after teardown.

---

## 4. Exposure model

The manager should support:

- hidden/internal-only workloads;
- local preview workloads with generated URLs;
- managed service endpoints for databases and auxiliary services.

Preview URLs must be stable enough for the CP/UI to present them clearly.

---

## 5. Security rules

- no uncontrolled port exposure;
- explicit policy for network-enabled workloads;
- clear distinction between loopback-only and broader exposure;
- future remote routing disabled until explicit distributed support is built.

---

## 6. Future expansion

Later phases may add:

- multi-node routing;
- secure service-to-service trust;
- remote node addressing;
- overlay or relay networking.

Those are outside the first local milestone.

---

## 7. Validation requirements

The network manager is complete when:

- local preview workloads receive usable URLs;
- network-disabled workloads cannot reach external networks by policy;
- port collisions are prevented or surfaced clearly;
- teardown releases network resources safely.
