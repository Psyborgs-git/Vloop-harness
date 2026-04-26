# Architecture Decision Records

## ADR-001: Use FastAPI for API + WebSocket Layer
**Date**: 2026-04-26 (inferred)
**Status**: Accepted

### Context
The system needs HTTP CRUD endpoints, WebSocket state/event streams, and strong request validation.

### Decision
Adopt FastAPI as the primary backend interface framework.

### Consequences
- Easier async endpoint implementation and OpenAPI-friendly contracts.
- Tight coupling to Pydantic/FastAPI idioms.

## ADR-002: Default to SQLite, Support PostgreSQL Override
**Date**: 2026-04-26 (inferred)
**Status**: Accepted

### Context
Local-first developer workflow needs minimal setup while still allowing external DB usage.

### Decision
Use SQLite by default; allow PostgreSQL through `VLOOP_DB_URL`.

### Consequences
- Fast local onboarding.
- Migration/compatibility complexity if production PG diverges.

## ADR-003: Centralize Data Access via Repository Layer
**Date**: 2026-04-26 (inferred)
**Status**: Accepted

### Context
Direct ORM usage in routes leads to duplicated persistence logic and harder tests.

### Decision
All route modules use `Repository` for CRUD/queries.

### Consequences
- Better separation of concerns and testability.
- Repository can become large and require periodic refactoring.

## ADR-004: Enforce Tool Policy + Confirmation for Risky Actions
**Date**: 2026-04-26 (inferred)
**Status**: Accepted

### Context
Terminal/filesystem/browser/database tools can perform destructive operations.

### Decision
Route tool calls through policy engine with optional confirmation-token workflow.

### Consequences
- Improved safety and auditability.
- Slightly higher UX friction for high-risk actions.

## ADR-005: Keep Python as Orchestration Brain and React as Control UI
**Date**: 2026-04-26 (inferred)
**Status**: Accepted

### Context
The product combines execution orchestration, persistence, and dynamic UI workflows.

### Decision
Use Python for state/orchestration/AI integration and React for presentation/workflow UI.

### Consequences
- Clear separation by responsibility.
- Requires maintaining robust API contract between backend and frontend.

## ADR-006: Support Dual Frontend Modes (Dev Proxy + Static Dist)
**Date**: 2026-04-26 (inferred)
**Status**: Accepted

### Context
Developers need HMR, but runtime also needs production-style static serving.

### Decision
Use `HARNESS_DEBUG` to switch between proxy-to-Vite and `react/dist` static serving.

### Consequences
- Better developer ergonomics and deployment flexibility.
- More branching logic in proxy/static routing paths.
