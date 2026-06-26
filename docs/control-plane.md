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

## 3. Package structure

### `core/` — domain logic (no I/O except database)

| Module | Lines | Role |
|---|---|---|
| `core/agent_orchestrator.py` | ~363 | Agent CRUD, invocation dispatch, usage statistics. |
| `core/agent_templates.py` | ~110 | `AgentTemplate` dataclass and curated `TEMPLATES` list. |
| `core/agent_normalizer.py` | ~170 | Payload validation, row-to-dict mappers, slug generation. |
| `core/agent_invoker.py` | ~220 | DSPy invocation execution, event hooks, output parsing. |
| `core/agent.py` | ~10 | Re-export shim for backward compatibility. |
| `core/provider_service.py` | ~270 | Provider CRUD, LM building, secret lifecycle, testing. |
| `core/provider_types.py` | ~100 | `ProviderTypeSpec` dataclass, `PROVIDER_TYPES` catalog. |
| `core/mock_dspy_lm.py` | ~120 | Deterministic mock DSPy LM for smoke testing. |
| `core/gateway.py` | ~10 | Re-export shim for backward compatibility. |
| `core/database.py` | ~420 | `DatabaseBackend` interface + SQLite, PostgreSQL, DuckDB backends + factory. |
| `core/vector_store.py` | ~515 | `VectorStore` interface + pgvector, DuckDB, SQLite, Pinecone backends + factory. |
| `core/helpers.py` | ~25 | `now_iso`, `to_json`, `from_json` persistence helpers. |
| `core/store.py` | ~150 | Legacy `SQLiteState` — delegates helpers to `core.helpers`. |
| `core/ports.py` | ~16 | Abstract `IExecutionManager` interface. |
| `core/planner.py` | ~1 | Scaffold for planner/DAG builder. |
| `core/dag.py` | ~1 | Scaffold for workflow/DAG state. |

### `cp/` — runtime, HTTP API, window, config, events

| Module | Lines | Role |
|---|---|---|
| `cp/runtime.py` | ~280 | `ControlPlaneRuntime` — kernel session, heartbeat, event loop, delegation. |
| `cp/application.py` | ~80 | `ControlPlaneApplication` + `bootstrap()` entry point. |
| `cp/session.py` | ~55 | `SessionSnapshot` dataclass, timestamp helper, gRPC metadata builder. |
| `cp/snapshots.py` | ~110 | Snapshot builders — health, session, event, window, system, dependency, bootstrap. |
| `cp/workloads.py` | ~200 | Async workload gRPC operations + `_workload_to_dict`. |
| `cp/bootstrap.py` | ~15 | Re-export shim for backward compatibility. |
| `cp/http_server.py` | ~70 | `HttpShellServer` — threaded HTTP server lifecycle. |
| `cp/http_handler.py` | ~118 | `ControlPlaneHandler` — lightweight dispatch delegating to handlers. |
| `cp/http_responders.py` | ~55 | `write_json`, `write_error_json`, `write_html`, `write_file` helpers. |
| `cp/http_utils.py` | ~140 | Path parsing, query helpers, JSON body reading, fallback HTML. |
| `cp/http_api.py` | ~25 | Re-export shim + `MethodNotAllowedError`. |

#### `cp/handlers/` — route-specific HTTP handlers

| Module | Lines | Role |
|---|---|---|
| `cp/handlers/__init__.py` | ~15 | Package re-export; imports all sub-modules for route registration. |
| `cp/handlers/router.py` | ~141 | Generic pattern-matching URL router with wildcard support. |
| `cp/handlers/system.py` | ~110 | Health, session, events, window, deps, shutdown, bootstrap, system snapshot, usage. |
| `cp/handlers/providers.py` | ~116 | Provider CRUD, catalog (4 alias paths), test, secret deletion. |
| `cp/handlers/agents.py` | ~119 | Agent CRUD, templates, validate, invoke. |
| `cp/handlers/invocations.py` | ~106 | Invocation list/get, events (path-based + query-param-based legacy). |
| `cp/handlers/settings.py` | ~85 | Database config GET/PUT, connection test. |
| `cp/handlers/workloads.py` | ~85 | Workload CRUD, start/stop, logs. |
| `cp/config_service.py` | ~142 | Typed config from kernel-injected active config and environment. |
| `cp/events.py` | ~76 | Kernel event subscription and fan-out to frontend. |
| `cp/window.py` | ~275 | PyWebView window lifecycle, focus, quit handling. |

### `adapters/` — infrastructure adapters

| Module | Lines | Role |
|---|---|---|
| `adapters/rust_infra.py` | ~14 | Scaffold for production execution via kernel gRPC. |

---

## 4. External APIs

### Frontend-facing APIs

The CP exposes:

- **Health & status**: `GET /health`, `GET /session`, `GET /window`, `GET /events/recent`, `GET /dependencies`
- **Bootstrap**: `GET /api/v1`, `GET /api/v1/bootstrap`, `GET /api/v1/state`
- **Provider catalog**: `GET /api/v1/catalog/provider-types`
- **Providers**: CRUD at `GET/POST /api/v1/providers`, `GET/PUT/DELETE /api/v1/providers/:id`, `POST /api/v1/providers/:id/test`, `DELETE /api/v1/providers/:id/secret`
- **Agent templates**: `GET /api/v1/agents/templates`
- **Agents**: CRUD at `GET/POST /api/v1/agents`, `GET/PUT/DELETE /api/v1/agents/:id`, `POST /api/v1/agents/validate`, `POST /api/v1/agents/:id/invoke`
- **Invocations**: `GET/POST /api/v1/invocations`, `GET /api/v1/invocations/:id`, `GET /api/v1/invocations/:id/events`, `GET /api/v1/invocation-events`
- **Usage**: `GET /api/v1/usage`
- **Settings**: `GET/POST /api/v1/settings/database`, `POST /api/v1/settings/database/test`
- **Workloads**: `GET/POST /api/v1/workloads`, `GET/DELETE /api/v1/workloads/:id`, `POST /api/v1/workloads/:id/start`, `POST /api/v1/workloads/:id/stop`, `GET /api/v1/workloads/:id/logs`
- **Shutdown**: `POST /shutdown`

### Kernel-facing APIs

The CP:

- registers with the kernel at startup;
- maintains a session and heartbeat;
- requests workloads, filesystems, databases, networks, and secret grants through kernel gRPC only;
- subscribes to kernel event streams.

---

## 5. Workflow model

A workflow includes:

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

The inference gateway centralizes:

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

## 8. Architecture decisions

### Single-file → multi-module refactor (June 2026)

The codebase was refactored from a few bulky files (500–900 lines each) into focused, single-concern modules averaging 50–280 lines. Key principles:

- **Backward compatibility**: Original modules (`agent.py`, `gateway.py`, `bootstrap.py`, `http_api.py`) are now re-export shims that import from the new sub-modules. All existing import paths continue to work.
- **No circular imports**: Internal module functions (normalizers, row mappers, event writers) avoid importing orchestrator/service classes. When a class reference is needed, `TYPE_CHECKING` guards are used.
- **Separation by concern**: Validation is separate from CRUD, invocation execution is separate from orchestration, mock providers are separate from real ones, HTTP routing is separate from response formatting.
- **`core/store.py` legacy**: `SQLiteState` is retained for backward compatibility but `core/database.py` should be used for new code. Helper functions (`now_iso`, `to_json`, `from_json`) now live in `core/helpers.py`.

---

## 9. Validation requirements

The CP is complete when it can:

- register with `vloopd` successfully;
- serve the frontend and open a window;
- dispatch a workflow that requests a kernel-managed workload;
- stream status/logs/events back to the frontend;
- enforce inference budgets and request secret grants without handling raw secret values.