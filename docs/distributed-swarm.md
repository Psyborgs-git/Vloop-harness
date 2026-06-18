# Distributed Swarm Specification

Distributed swarm is the later-stage multi-node execution model for VLoop. It is intentionally deferred until the single-node local platform and Kubernetes backend are stable.

---

## 1. Purpose

Swarm extends VLoop from one trusted local node to multiple cooperating nodes while preserving:

- kernel-owned infrastructure authority per node;
- strong trust and identity boundaries;
- explicit routing and scheduling decisions;
- capability-scoped secret and workload behavior.

---

## 2. High-level design

Each node should run:

- its own `vloopd`;
- its own CP if needed for local UX;
- a secure remote control plane for node-to-node coordination only when enabled.

---

## 3. Required building blocks

| Capability | Description |
|---|---|
| node identity | stable identity and trust material per node |
| secure transport | mTLS or equivalent strong node authentication |
| scheduler/inventory | resource inventory and placement logic |
| remote routes | workload, service, and artifact routing across nodes |
| capability propagation | tightly scoped remote grants |

---

## 4. Design constraints

- swarm is disabled by default;
- remote APIs are a separate trust boundary from local IPC;
- no raw secret transfer between nodes;
- scheduling must respect locality, policy, and failure domains.

---

## 5. Not part of the first production milestone

Swarm should remain a blueprint and interface placeholder until:

1. local single-node operation is robust;
2. packaging and service management are stable;
3. Kubernetes support is in place where needed;
4. observability and security controls are mature enough for remote execution.
