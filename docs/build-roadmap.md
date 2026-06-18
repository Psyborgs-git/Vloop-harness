# Build Roadmap

This roadmap describes the greenfield construction order for VLoop.

---

## Stage 1 — Kernel foundation

Deliver:

- `kernel/` crate
- `vloopd`, `vloopctl`, `vloop-launcher`
- foreground daemon boot
- basic service integration scaffolds

Gate:

- binaries build and start
- launcher and control utility shells exist

---

## Stage 2 — Local IPC and CP registration

Deliver:

- `proto/kernel.proto`
- local IPC transport by OS
- kernel registration and heartbeat path
- CP bootstrap registration

Gate:

- CP can register and report health through the kernel

---

## Stage 3 — Frontend and CP shell

Deliver:

- CP HTTP API
- CP-owned window runtime
- React shell connected to CP health/status

Gate:

- app opens through launcher and shows live health state

---

## Stage 4 — Workload orchestration + Docker backend

Deliver:

- workload state machine
- Docker-backed execution
- logs and status streams
- preview URL exposure

Gate:

- one end-to-end workflow can run in a Docker-managed sandbox

---

## Stage 5 — Kernel managers

Deliver:

- filesystem manager
- database manager
- network manager
- secret manager
- dependency manager

Gate:

- CP can request managed resources and consume returned capabilities/config

---

## Stage 6 — Real workflow engine

Deliver:

- planner/DAG engine
- agent orchestration
- inference gateway
- approvals and event routing

Gate:

- a user can create, observe, cancel, and retry workflows in the UI

---

## Stage 7 — Packaging

Deliver:

- macOS package and LaunchAgent flow
- Windows package and service flow
- Linux package and systemd user-service flow

Gate:

- install, open, restart, and uninstall work on all target OSes

---

## Stage 8 — Kubernetes backend

Deliver:

- K8s workload support
- DB/service mapping where needed
- log/event parity with local runtime

Gate:

- the same workload intent can run locally or on Kubernetes

---

## Stage 9 — Distributed swarm

Deliver:

- future node identity
- future secure remote routing
- future multi-node scheduling and policy

Gate:

- only after local and Kubernetes phases are stable
