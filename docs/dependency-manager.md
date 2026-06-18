# Dependency Manager Specification

The dependency manager is the kernel subsystem that ensures the host is ready to run VLoop and that the CP receives an accurate, dynamic runtime configuration.

---

## 1. Responsibilities

- detect, validate, and in some cases install required runtime dependencies;
- manage bundled runtime assets where appropriate;
- prepare Python CP runtime expectations;
- prepare or validate Docker readiness;
- validate database/runtime service prerequisites;
- generate active configuration injected into the CP;
- support `vloopctl doctor`.

---

## 2. Managed dependency classes

| Class | Examples |
|---|---|
| container runtime | Docker Desktop / Docker Engine |
| Python runtime assets | bundled runtime, environment, package sync strategy |
| database images/services | Postgres, Redis, vector runtime assets |
| static UI bundle | built frontend assets served by the CP |
| service metadata | version compatibility and release assets |

---

## 3. Readiness model

The manager should classify dependencies as:

- `ready`
- `missing`
- `installed_but_not_running`
- `version_mismatch`
- `degraded`

These states should feed daemon health and `doctor` output.

---

## 4. Active config injection

The kernel should inject dynamic configuration into the CP including:

- IPC endpoint information;
- CP session/grant context;
- available runtimes;
- database endpoints and capability references;
- resource budgets;
- feature availability;
- version and compatibility data.

The CP should treat the kernel as the runtime configuration authority for infrastructure-backed concerns.

---

## 5. `doctor` support

The manager should power `vloopctl doctor` with:

- Docker readiness checks;
- CP runtime and version checks;
- runtime directory and permission checks;
- local service registration checks;
- DB readiness checks;
- bundle/version consistency checks.

---

## 6. Update and compatibility policy

The dependency manager should enforce:

- version compatibility between kernel, CP, proto contract, and UI bundle;
- clear behavior during upgrades;
- actionable remediation when a dependency becomes invalid.

---

## 7. Validation requirements

The dependency manager is complete when:

- `doctor` can explain why the product is or is not ready;
- the CP receives all runtime-critical configuration dynamically from the kernel;
- missing dependencies can be surfaced clearly to a non-technical user.
