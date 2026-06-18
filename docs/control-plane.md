# Python Control Plane Specification

The Python Control Plane is the cognitive authority in VLoop. It owns agent orchestration, inference, workflow state, windows, and user interaction. It does **not** own infrastructure execution.

---

## 1. Responsibilities

The CP is responsible for:

- bootstrapping and registering with `vloopd`;
- serving the frontend and owning user-visible windows;
- exposing HTTP/WebSocket APIs to the frontend;
- running the agent orchestration engine;
- planning workflows and persisting workflow state;
- managing inference policy, budgets, and provider routing;
- translating kernel event streams into user-facing workflow state.

## 2. Non-responsibilities

The CP does **not**:

- call Docker or Kubernetes directly in the production path;
- store or return raw secrets by default;
- own local resource truth for files, networks, databases, or workloads;
- bypass the kernel for arbitrary execution.

---

## 3. Internal structure

| Module | Role |
|---|---|
| `cp/bootstrap.py` | Starts the CP runtime, config loading, kernel registration, and service startup. |
| `cp/http_api.py` | Frontend-facing HTTP and WebSocket API. |
| `cp/window.py` | PyWebView or equivalent window management. |
| `cp/config_service.py` | Typed config from kernel-injected active config and user preferences. |
| `cp/events.py` | Kernel event subscription and fan-out to frontend and workflow state. |
| `core/agent.py` | Agent orchestration runtime. |
| `core/planner.py` | Goal compilation into workflows/DAGs/plans. |
| `core/dag.py` | Workflow persistence, state transitions, rewind/retry rules. |
| `core/gateway.py` | Inference gateway, budgets, model routing, caching, provider policies. |
| `adapters/rust_infra.py` | Production execution port backed by kernel gRPC. |

---

## 4. External APIs

### Frontend-facing APIs

The CP should expose:

- health and version endpoints;
- session and window-state endpoints;
- workflow create/read/cancel/retry endpoints;
- resource status streams;
- settings, vault UX, and support surfaces;
- WebSocket event feeds for logs, progress, and approvals.

### Kernel-facing APIs

The CP should:

- register with the kernel at startup;
- maintain a session and heartbeat;
- request workloads, filesystems, databases, networks, and secret grants through kernel gRPC only;
- subscribe to kernel event streams.

---

## 5. Workflow model

A workflow should include:

- a user objective;
- an execution plan or DAG;
- one or more agents/tools/steps;
- infrastructure requests;
- event history;
- artifacts;
- retry/cancel state;
- approval checkpoints where required.

The CP owns workflow meaning. The kernel owns resource reality.

---

## 6. Inference model

The inference gateway should centralize:

- provider selection;
- model profiles;
- budgets and rate limits;
- retries and fallbacks;
- tool-call and prompt policies;
- secret-backed provider authentication through kernel-granted capabilities.

---

## 7. Window ownership model

The CP owns window lifecycle:

- main application window;
- future modal or approval surfaces;
- open/focus/close behavior;
- initial boot/failure states before workflows are available.

The launcher gets the user to the CP. The CP owns the visible experience.

---

## 8. Validation requirements

The CP is complete when it can:

- register with `vloopd` successfully;
- serve the frontend and open a window;
- dispatch a workflow that requests a kernel-managed workload;
- stream status/logs/events back to the frontend;
- enforce inference budgets and request secret grants without handling raw secret values.
