# VLoop

VLoop is a cross-platform, local-first AI orchestration platform built from the ground up around two authorities:

- **`vloopd`** — the Rust infrastructure daemon;
- **Python Control Plane** — the orchestration, inference, and GUI authority.

The repository is now organized as a greenfield build:

- `kernel/` — Rust daemon, service control, IPC, and infrastructure managers
- `control-plane/` — Python Control Plane
- `src/` — React frontend served by the CP
- `proto/` — canonical gRPC contracts
- `packaging/` — OS-native packaging assets
- `docs/` — architecture blueprint and subsystem specifications

## Start here

- Architecture overview: [`docs/fix-plan.md`](docs/fix-plan.md)
- Build order: [`docs/build-roadmap.md`](docs/build-roadmap.md)

## Core subsystem docs

- [`docs/vloopd.md`](docs/vloopd.md)
- [`docs/vloopctl.md`](docs/vloopctl.md)
- [`docs/vloop-launcher.md`](docs/vloop-launcher.md)
- [`docs/control-plane.md`](docs/control-plane.md)
- [`docs/frontend.md`](docs/frontend.md)
- [`docs/kernel-ipc.md`](docs/kernel-ipc.md)
- [`docs/proto-contract.md`](docs/proto-contract.md)
- [`docs/workload-orchestrator.md`](docs/workload-orchestrator.md)
- [`docs/docker-backend.md`](docs/docker-backend.md)
- [`docs/filesystem-manager.md`](docs/filesystem-manager.md)
- [`docs/database-manager.md`](docs/database-manager.md)
- [`docs/network-manager.md`](docs/network-manager.md)
- [`docs/secret-manager.md`](docs/secret-manager.md)
- [`docs/dependency-manager.md`](docs/dependency-manager.md)
- [`docs/packaging.md`](docs/packaging.md)
- [`docs/security-model.md`](docs/security-model.md)
- [`docs/kubernetes-backend.md`](docs/kubernetes-backend.md)
- [`docs/distributed-swarm.md`](docs/distributed-swarm.md)

## Product architecture in one sentence

The Python Control Plane decides **what** should happen; the Rust kernel decides **how and where** it runs.
