# Full-Stack Agents Harness Plan

This document updates the current VLoop Harness plan for the next version: a
self-programming, full-stack agents harness that can use DSPy components and
pipelines to design, write, test, persist, and operate reusable backend logic
and React UIs with controlled autonomy.

## Target product

VLoop should become a local-first agent operating system with:

- **DSPy agent brain**: reusable DSPy signatures/modules, optimizers, evaluators,
  and pipelines that can create new DSPy components from natural-language specs.
- **Dynamic execution layer**: safe terminal, filesystem, browser, database, and
  application-runtime tools exposed through a unified registry and policy system.
- **Persistent working memory**: project database, chat history, generated
  components, generated React views, tool traces, run artifacts, and execution
  state.
- **Dynamic frontend layer**: generated React views that can be mounted,
  inspected, edited, versioned, and connected to Python/DSPy backends.
- **Autonomous coding loop**: plan → generate → write files → run tests/builds →
  inspect browser/UI → persist results → ask for confirmation only when policy
  requires it.
- **Operator control plane**: chat-first command center plus a window manager for
  generated apps, logs, tool approvals, database inspection, and pipeline runs.

## Current implementation parity

| Capability | Current status | Parity |
| --- | --- | --- |
| Python component lifecycle | `BaseComponent`, `ComponentTree`, `ProcessManager`, state updates, events, and lifecycle hooks exist. | High |
| FastAPI bridge | Component REST routes, WebSockets, root route, proxy, settings, chat, DSPy, tools, and views routes exist. | High |
| DSPy engine | Provider config, async `DSPyEngine`, built-in reasoning/code/QA/summarize/chat/view/spec modules, and custom module execution exist. | High |
| DSPy component registry | Generated/saved component definitions are persisted and can be loaded for pipeline execution. | Medium |
| Pipelines | DSPy component steps and tool steps can execute, including confirmation pauses. | Medium |
| Terminal tool | Safe subprocess execution, policy gating, workspace boundaries, output limits, and injection checks exist. | High |
| Filesystem tool | Safe list/read/stat/write/create/delete/move operations with confirmations exist. | High |
| Browser tool | Not implemented as a harness tool. Playwright exists only for tests. | None |
| Database tool | SQLAlchemy persistence exists, but no policy-gated query/admin tool exists for agents. | Low |
| Persistence | Chat sessions/messages, DSPy components, pipelines, providers, telemetry, and generated views are persisted. | High |
| Generated React views | View generation, validation, disk write, DB storage, and UI listing exist. | Medium |
| Dynamic full-stack app mounting | `/ui/{component_id}` proxy exists, but the root UI is chat-first and lacks a floating iframe/window manager. | Low |
| Autonomous self-modification loop | Pieces exist through chat, DSPy, tools, and generated views, but no orchestrated agent loop owns planning, edits, tests, browser inspection, and rollback. | Low |
| Security/approval model | Tool policy, permissions, and confirmations exist; broader autonomy budgets and audit trails need expansion. | Medium |

## Updated architecture plan

### 1. Agent control plane

Create an agent runtime that coordinates requests from chat and pipelines into
durable task runs.

- Add an `AgentRun` domain model with goal, plan, status, steps, tool calls,
  generated artifacts, approvals, errors, and final result.
- Add an agent orchestrator service that can invoke DSPy modules, run pipelines,
  call tools, generate files, request confirmation, and resume paused runs.
- Store every run step as an append-only audit log tied to chat sessions and
  generated artifacts.
- Expose APIs for starting, pausing, resuming, cancelling, and replaying runs.
- Surface run state in the root UI as a timeline with tool outputs and approval
  prompts.

### 2. DSPy component factory

Turn the existing DSPy component generation into a reusable component factory.

- Define a stable component package format: metadata, DSPy signature fields,
  module source, tests/evals, example inputs, dependencies, and version.
- Extend generated component validation beyond syntax to include import safety,
  signature conformance, deterministic smoke tests, and optional DSPy evals.
- Add compile/load/version flows for generated DSPy modules.
- Add a component marketplace/library UI for search, activation, cloning, and
  reuse inside pipelines.
- Add evaluation datasets and optimizer configuration per component so the
  harness can improve generated modules over time.

### 3. Full-stack app and React view factory

Connect generated React views to generated Python/DSPy backends as first-class
apps.

- Define an app manifest that links a Python component or DSPy pipeline to one
  or more React views, permissions, routes, state schema, and generated files.
- Generate both backend logic and frontend UI from a single app spec.
- Validate React output with TypeScript and isolated rendering checks before
  making it available in the UI.
- Version generated views and keep file paths, source, prompts, run IDs, and
  validation results in the database.
- Add promotion states: draft, validated, active, archived.

### 4. Root UI evolution

Keep the existing chat-first dashboard as the command center, then add the
documented window manager.

- Preserve ChatPanel as the primary instruction surface.
- Add a workspace mode with floating/resizable generated app windows backed by
  iframes served from `/ui/{component_id}` or generated view routes.
- Add a view registry/sidebar for generated views, DSPy components, pipelines,
  running agent tasks, logs, and tool approvals.
- Persist window layout, focused view, minimized state, and opened artifacts.
- Let agent runs open generated apps automatically after validation.

### 5. Tool runtime expansion

Extend the existing policy-gated tool registry.

- Add a browser tool backed by Playwright for navigation, screenshots, DOM
  inspection, form interaction, and UI validation with strict origin/workspace
  policy.
- Add a database tool for schema inspection, safe parameterized reads, migrations
  generated through reviewable files, and restricted write/admin actions behind
  confirmation.
- Add structured tool traces that include inputs, sanitized outputs, duration,
  risk level, confirmation tokens, and artifact links.
- Add per-agent and per-pipeline permission budgets so autonomous loops cannot
  exceed approved scopes.
- Add replayable tool-call fixtures for deterministic tests of agent behavior.

### 6. Persistence, memory, and artifacts

Unify storage around the SQLAlchemy data layer while preserving project-local
files for source artifacts.

- Add tables for agent runs, run steps, generated artifacts, app manifests,
  tool traces, eval results, and view versions.
- Keep generated code in the repository workspace and store metadata plus hashes
  in the database.
- Add migrations or schema bootstrap checks for all new tables.
- Add retention and export flows for chats, runs, generated apps, and telemetry.
- Make `.vloop/` the local operational store for logs, temporary artifacts,
  policy, and private configuration.

### 7. Safety, autonomy, and governance

Autonomy must be explicit, observable, and reversible.

- Define autonomy modes: observe-only, suggest-only, write-with-approval,
  test-with-approval, and autonomous-with-budget.
- Require confirmations for destructive filesystem/database actions, external
  network/browser actions outside policy, dependency changes, and secret access.
- Add diff previews before generated code is activated.
- Add rollback for generated files and app manifests.
- Add secret redaction in tool traces, chat transcripts, telemetry, and logs.
- Add security scans for generated code before promotion to active status.

### 8. Developer and operator workflow

The end-to-end loop should be:

1. User describes a desired capability in chat.
2. Agent creates a durable plan and requests scope/permission approval if needed.
3. DSPy component factory generates or selects backend modules.
4. React view factory generates UI tied to component/pipeline state and events.
5. Filesystem tool writes draft artifacts.
6. Terminal tool runs Python tests, TypeScript checks, and targeted builds.
7. Browser tool opens the generated UI and verifies interaction.
8. Database stores run trace, generated components, generated views, artifacts,
   validation results, and final app manifest.
9. Root UI opens the generated app in the workspace.
10. User can refine, version, archive, or publish the result.

## Implementation phases

### Phase 1: Align docs and data model

- Mark the current root UI as chat-first and the window manager as planned.
- Add database models/repository methods for agent runs, steps, artifacts, app
  manifests, tool traces, and eval results.
- Add API contracts for agent runs and app manifests.
- Add a parity/status page in the UI or docs.

### Phase 2: Agent run orchestration

- Implement the durable agent run service.
- Wire chat actions to create agent runs instead of one-off ad hoc generation.
- Record DSPy calls, tool calls, generated files, confirmations, and results as
  run steps.
- Add pause/resume/cancel support.

### Phase 3: Component and view factories

- Formalize generated DSPy component packages.
- Add validation, versioning, and activation flows.
- Link generated React views to backend components/pipelines through app
  manifests.
- Add TypeScript validation for generated views before activation.

### Phase 4: Browser and database tools

- Implement the Playwright browser tool with policy checks and sanitized traces.
- Implement the database inspection/query tool with read/write risk classes.
- Add UI panels for browser sessions, DB schema/query views, and tool traces.
- Add pipeline/tool examples using terminal, filesystem, browser, and database
  tools.

### Phase 5: Workspace window manager

- Add a root workspace mode with iframe-backed generated app windows.
- Persist layouts and view state.
- Allow agent runs to open, close, focus, and inspect generated app views through
  controlled UI APIs.
- Keep the chat dashboard available as the command center.

### Phase 6: Autonomous improvement loop

- Add eval datasets, optimizer configs, and regression suites for generated DSPy
  modules.
- Let agents propose component upgrades, run evals, compare results, and promote
  better versions with approval.
- Add rollback and artifact provenance across code, UI, prompts, and evals.

## Acceptance criteria for the new version

- A user can ask for a new capability and receive a generated DSPy component,
  pipeline, Python/runtime integration, and React UI as a versioned app.
- The app can be mounted in the root workspace, interacted with in the browser,
  and refined through chat.
- The harness can run terminal, filesystem, browser, and database tools through
  one policy-gated registry.
- Every autonomous action is stored as a durable, inspectable run step.
- Generated code is validated before activation and can be rolled back.
- The system can reuse prior generated DSPy components and views in new
  pipelines/apps.
- The current chat-first UI remains usable while the window manager adds dynamic
  app workspaces.

## Immediate documentation changes from the current plan

- Treat the README window-manager diagrams as target architecture, not current
  implementation.
- Treat browser and database tools as planned tool-runtime expansions.
- Treat generated React views as draft artifacts until they are connected to app
  manifests and workspace mounting.
- Treat autonomous self-modification as an orchestrated agent-run feature still
  to be implemented on top of existing DSPy, chat, tools, and persistence pieces.
