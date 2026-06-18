# Docker Backend Specification

Docker is the default local runtime backend for VLoop. It is the first implementation target for local workload execution across all supported platforms.

---

## 1. Why Docker first

- it is the most common cross-platform local container runtime;
- it is broadly available on macOS and Windows through Docker Desktop;
- it provides a clear early path for local parity before Kubernetes and swarm features are added.

---

## 2. Platform assumptions

| OS | Expected runtime |
|---|---|
| macOS | Docker Desktop |
| Windows | Docker Desktop |
| Linux | Docker Engine or equivalent Docker-compatible runtime |

The dependency manager must validate readiness and surface setup guidance.

---

## 3. Backend responsibilities

- image pull and presence checks;
- container create/start/inspect/stop/remove;
- volume and bind mount setup using kernel-managed paths only;
- port mapping discovery;
- network selection and policy mapping;
- log collection and exec support;
- resource limits and timeout behavior.

---

## 4. Workload spec mapping

A Docker-backed workload should map from a kernel spec into:

- image
- command and args
- environment references
- managed mounts
- CPU/memory limits
- network mode/policy
- exposed ports
- labels/metadata for reconciliation

---

## 5. Security rules

- no arbitrary host path mounting from the CP;
- secret injection only from kernel grants;
- network access controlled by explicit policy;
- images should be pulled or whitelisted according to product policy;
- logs must redact secrets where possible.

---

## 6. Failure handling

The backend should detect and report:

- Docker unavailable;
- image pull failure;
- container create failure;
- runtime exit failure;
- stuck teardown or resource leak conditions.

---

## 7. Validation requirements

The Docker backend is complete when:

- a simple worker workload runs on all target OSes;
- preview workloads can expose stable local URLs through the network manager;
- teardown leaves no silent orphan containers;
- missing Docker is surfaced clearly through `vloopctl doctor`.
