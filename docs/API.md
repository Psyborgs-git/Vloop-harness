# API Reference

Base URL: `http://<HARNESS_HOST>:<HARNESS_PORT>` (default `http://localhost:8000`)

## REST/HTTP API

### [GET] /
**Description**: Service health/status root.
**Authentication**: None.
**Response**: `200` with `{status, service, version}`.

## Component Runtime (`/api/components` + dynamic `/api/{component_id}`)
### [GET] /api/components
Lists live registered components.
### [POST] /api/components
Creates component from Python class path.
Body: `{ class_path, props, permissions[] }`.
### [DELETE] /api/components/{component_id}
Unregisters/destroys component.
### [GET] /api/{component_id}/state
Returns component snapshot.
### [POST] /api/{component_id}/event
Body: `{ name, payload }`; forwards event to component.
### [POST] /api/{component_id}/props
Body: `{ props }`; updates component props.
### [GET] /api/{component_id}/logs?n=100
Returns recent logs.

Errors: `404` component not found, `400` import/validation errors.

## WebSockets
### [WS] /ws/root
Dashboard keep-alive WS.
### [WS] /ws/{component_id}
Bidirectional component event/state channel.
Initial server message: `{type:"state_update", data:<state>}`.

## Chat (`/api/chat`)
### [GET] /api/chat/sessions
### [POST] /api/chat/sessions
Body: `{ title }`.
### [GET] /api/chat/sessions/{session_id}
### [PATCH] /api/chat/sessions/{session_id}
Body: `{ title }`.
### [DELETE] /api/chat/sessions/{session_id}
### [GET] /api/chat/sessions/{session_id}/messages
### [GET] /api/chat/sessions/{session_id}/transcript
### [POST] /api/chat/sessions/{session_id}/messages
Body: `{ content }`; persists user message and returns assistant response.

Common errors: `404` session not found, `500` model/runtime failures.

## DSPy Components & Pipelines (`/api/dspy`)
### Components
- `[GET] /api/dspy/components`
- `[POST] /api/dspy/components` body `{name, description, code, module_type}`
- `[GET] /api/dspy/components/{component_id}`
- `[PUT] /api/dspy/components/{component_id}` partial body fields
- `[DELETE] /api/dspy/components/{component_id}`
- `[POST] /api/dspy/components/{component_id}/run` body `{inputs:{...}}`

### Pipelines
- `[GET] /api/dspy/pipelines`
- `[POST] /api/dspy/pipelines` body `{name, description, steps[]}`
- `[GET] /api/dspy/pipelines/{pipeline_id}`
- `[PUT] /api/dspy/pipelines/{pipeline_id}`
- `[DELETE] /api/dspy/pipelines/{pipeline_id}`
- `[POST] /api/dspy/pipelines/{pipeline_id}/run` body `{inputs:{...}}`

Compile/validation errors return `422`; missing records return `404`.

## Evaluation & Versioning (`/api/dspy/components/{component_id}`)
- `[GET] /versions`
- `[POST] /snapshot` body `{change_summary}`
- `[POST] /rollback` body `{version_id}`
- `[GET] /eval-datasets`
- `[POST] /eval-datasets` body `{name,description,examples[]}`
- `[PUT] /eval-datasets/{dataset_id}`
- `[DELETE] /eval-datasets/{dataset_id}`
- `[POST] /evaluate` body `{dataset_id}`

## Views (`/api/views`)
- `[POST] /api/views/generate` body `{description, component_name, spec, session_id}`
- `[GET] /api/views`
- `[DELETE] /api/views/{view_id}`

Generation may return `503` if AI engine is not configured.

## Providers & Settings
- `[GET] /api/settings`
- `[PUT] /api/settings` body `{settings:{...}}`
- `[GET] /api/providers`
- `[POST] /api/providers`
- `[GET] /api/providers/{provider_id}`
- `[PUT] /api/providers/{provider_id}`
- `[DELETE] /api/providers/{provider_id}`
- `[POST] /api/providers/{provider_id}/set-default`
- `[GET] /api/providers/{provider_id}/test`
- `[GET] /api/ollama/models?base_url=...`

## Agent Runs (`/api/agents`)
- `[POST] /api/agents/runs` body `{goal, session_id, autonomy_mode, context}`
- `[GET] /api/agents/runs?limit=50`
- `[GET] /api/agents/runs/{run_id}`
- `[POST] /api/agents/runs/{run_id}/cancel`
- `[POST] /api/agents/runs/{run_id}/resume` body `{confirmed_token}`
- `[DELETE] /api/agents/runs/{run_id}`

## App Manifests (`/api/apps`)
- `[POST] /api/apps/manifests`
- `[GET] /api/apps/manifests?status=...`
- `[GET] /api/apps/manifests/{manifest_id}`
- `[PUT] /api/apps/manifests/{manifest_id}`
- `[POST] /api/apps/manifests/{manifest_id}/promote` body `{status}`
- `[DELETE] /api/apps/manifests/{manifest_id}`
- `[GET] /api/apps/traces` (tool trace listing)

## Tools (`/api/tools`)
- `[GET] /api/tools`
- `[GET] /api/tools/policy`
- `[PUT] /api/tools/policy`
- `[GET] /api/tools/workspace`
- `[POST] /api/tools/terminal`
- `[POST] /api/tools/filesystem/list|read|stat|write|create|delete|move`
- `[POST] /api/tools/browser`
- `[POST] /api/tools/database`
- `[POST] /api/tools/confirm/{token}`
- `[DELETE] /api/tools/confirm/{token}`

Some tool operations return `202 Accepted` with `{requires_confirmation:true, token,...}`.

## UI Serving Endpoints
- `[GET] /ui/root` and `/ui/root/{path}`
- `[GET] /ui/{component_id}` and `/ui/{component_id}/{path}`
- `[GET] /src/{path}`, `/@{path}`, `/node_modules/{path}` (debug mode pass-through)

## Authentication & Authorization
No user authentication middleware is implemented for API access (trusted local environment model). Authorization for dangerous actions is policy-based at tool runtime level, plus optional confirmation tokens.

## Rate Limiting
No explicit server-side rate-limiting middleware is implemented in this codebase today. Clients should implement retry/backoff on failures and avoid burst traffic against long-running AI/tool endpoints.

## Error Format
Common FastAPI error shape:
```json
{"detail": "..."}
```
Tool confirmation special-case (`202`):
```json
{
  "requires_confirmation": true,
  "token": "...",
  "description": "...",
  "risk_level": "...",
  "expires_in_seconds": 60
}
```

## Versioning
Current API versioning is path-implicit and not namespace-versioned (no `/v1`). Service root and FastAPI app metadata report `0.2.0`. Deprecation policy for this repository is: mark endpoint behavior changes in `docs/CHANGELOG.md`, keep backward compatibility for additive changes, and treat removals/contract-breaking changes as release-gated maintainer decisions.
