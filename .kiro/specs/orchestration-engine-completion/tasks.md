# Implementation Plan: Orchestration Engine Completion

## Overview

This plan completes the VLoop Control_Plane orchestration engine in Python under `control-plane/`, building from pure-logic core (serializer, DAG, planner, cron) outward to the DAG executor, inference gateway/policy layer, capability subsystems, the kernel execution adapter, the HTTP/WebSocket API, and finally the React frontend views.

Tasks are ordered for incremental, test-driven progress: each task builds on prior tasks and ends by wiring its subsystem into the run path so no orphaned code remains. Property-based tests use Hypothesis (minimum 100 examples each, one test per property, tagged `# Feature: orchestration-engine-completion, Property N: ...`). Each property test lives in its own file under `control-plane/tests/`. All kernel touchpoints are written against the `RustInfraExecutionManager` gRPC client and tested with mocks; the new kernel gRPC surface (sandbox Exec, FS Snapshot/Restore, Secret Grant) is a coordinated dependency.

Run tests with `pytest` (single execution, not watch mode).

## Tasks

- [x] 1. Persistence schema and shared orchestration types
  - [x] 1.1 Add orchestration tables to `core/database.py`
    - Add `workflow_definitions`, `workflow_runs`, `workflow_steps`, `workflow_events`, `scheduled_tasks`, `memory_entries`, `checkpoints`, `toolsets`, `mcp_servers` to `_SCHEMA_STATEMENTS`
    - Use existing `DatabaseBackend` (`fetch_all`/`fetch_one`/`execute`/`executemany`) and `core/helpers.to_json`/`from_json` for JSON columns
    - _Requirements: 3.7, 8.5, 11.1, 13.4, 14.1, 18.1_
  - [x] 1.2 Write unit tests for schema creation and persistence round-trip
    - Verify each table is created across the SQLite backend and a row inserts/reads back via `DatabaseBackend`
    - _Requirements: 3.7, 14.1_
  - [x] 1.3 Define shared orchestration dataclasses in `core/orchestration_types.py`
    - `ModelRequest`, `RoutingPolicy`, `RunScope`, `GrantContext`, `Budget`, `ToolScope`, `ToolSpec`, `ToolsetSpec`, `StepResult` and run/step state enums
    - `GrantContext` carries only `grant_id`/`session_ref` (never raw secret values)
    - _Requirements: 6.5, 7.1, 9.2, 16.4, 19.1_

- [x] 2. Workflow_Serializer (`core/workflow_serializer.py`)
  - [x] 2.1 Implement canonical serialize/deserialize with malformed-input handling
    - Emit sorted-key JSON over the `{version, name, objective, inputs, steps[{id,type,config,dependsOn}], policies}` shape for byte-stable re-serialization
    - Return a descriptive error (no unhandled exception) for malformed serialized input
    - _Requirements: 2.1, 2.2, 2.3, 2.4_
  - [x] 2.2 Write property test for serializer round-trip
    - **Property 4: Workflow_Serializer round-trip** — `serialize(deserialize(serialize(d))) == serialize(d)`
    - **Validates: Requirements 2.1, 2.2, 2.3**
    - Use a `workflow_definitions()` Hypothesis strategy
  - [x] 2.3 Write property test for malformed input handling
    - **Property 5: Workflow_Serializer rejects malformed input gracefully**
    - **Validates: Requirements 2.4**
    - Use a `serialized_definitions()` strategy emitting corrupted/garbage forms

- [x] 3. DAG model (`core/dag.py`)
  - [x] 3.1 Flesh out `DagNode`/`Dag` with topology helpers
    - Implement `detect_cycle`, `topological_layers`, `dependents_of` (transitive), `roots`
    - _Requirements: 1.1, 1.2, 3.2_
  - [x] 3.2 Write unit tests for cycle detection and topology helpers
    - Cover acyclic/cyclic graphs, transitive dependents, layering
    - _Requirements: 1.2, 3.2_

- [x] 4. Planner (`core/planner.py`)
  - [x] 4.1 Implement `Planner` and `ReferenceResolver`
    - `build_dag` compiles a definition into a validated `Dag`; `validate` returns problems side-effect free
    - Reject cycles (naming involved steps) and missing agent/tool/input references (naming the reference); never persist or assign an id on rejection
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_
  - [x] 4.2 Write property test for faithful DAG build and id assignment
    - **Property 1: Planner builds a faithful DAG for valid definitions and assigns an id only then**
    - **Validates: Requirements 1.1, 1.4**
  - [x] 4.3 Write property test for invalid-definition rejection
    - **Property 2: Invalid definitions (cycles and missing references) are rejected and named**
    - **Validates: Requirements 1.2, 1.3**
    - Use `workflow_definitions()` cycle and unknown-reference variants
  - [x] 4.4 Write property test for side-effect-free validation
    - **Property 3: Validation is side-effect free** — zero model calls and zero kernel workloads
    - **Validates: Requirements 1.5**
    - Assert against mock gateway/kernel call counters

- [x] 5. Cron_Parser (`core/cron_parser.py`)
  - [x] 5.1 Implement cron parse/format
    - Parse a cron expression into a `Schedule` and format a `Schedule` back to a cron expression
    - _Requirements: 14.4_
  - [x] 5.2 Write property test for cron round-trip
    - **Property 35: Cron_Parser round-trip** — `parse(format(parse(e)))` equals `parse(e)`
    - **Validates: Requirements 14.4**
    - Use a `cron_expressions()` strategy across all fields

- [x] 6. Checkpoint - pure-logic core
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Kernel execution adapter (`adapters/rust_infra.py`)
  - [x] 7.1 Implement sandbox exec, teardown, and log streaming
    - `dispatch_job` (sandbox exec via new `WorkloadControl.Exec`), `stream_logs`, `teardown` against the kernel gRPC client; block with no host fallback if sandbox routing fails
    - _Requirements: 16.1, 16.2, 16.3, 21.1, 21.2_
  - [x] 7.2 Implement workspace snapshot/restore
    - `snapshot_workspace` and `restore_workspace` via new `FilesystemControl.Snapshot`/`.Restore`; store only the returned snapshot reference
    - _Requirements: 13.1, 13.2, 13.4_
  - [x] 7.3 Implement secret-grant consumption
    - `request_secret_grant` via `SecretControl.Grant` returning `GrantContext` (grant id + session ref only, no raw secret values)
    - _Requirements: 6.5, 16.4, 18.4, 18.5_
  - [x] 7.4 Write unit tests with a mocked gRPC stub
    - Verify exec/teardown/snapshot/restore/grant call the expected RPCs and that no raw secret value is retained; assert sandbox-routing failure raises with no host branch
    - _Requirements: 16.3, 21.2_

- [x] 8. Event_Router and secret redaction (`core/event_router.py`, extend `cp/events.py`)
  - [x] 8.1 Implement event normalization, run-id attribution, and redaction
    - Normalize kernel + internal orchestration events into user-facing workflow events, attach the `Workflow_Run` id to every event, persist to `workflow_events`, and redact secret values from payloads
    - _Requirements: 4.1, 21.4, 21.5_
  - [x] 8.2 Write property test for per-transition events
    - **Property 10: Every step transition emits a corresponding event**
    - **Validates: Requirements 4.1**
  - [x] 8.3 Write property test for secret redaction
    - **Property 45: Secrets are redacted from all outputs**
    - **Validates: Requirements 21.4**
  - [x] 8.4 Write property test for event run attribution
    - **Property 46: Every orchestration event is attributable to a run**
    - **Validates: Requirements 21.5**

- [x] 9. DAG_Executor core scheduling (`core/dag_executor.py`)
  - [x] 9.1 Implement run creation, ready-step scheduling, concurrency, persistence, and outcome derivation
    - `start_run` creates a run (unique id, `pending`); `_schedule_ready` runs steps only when all `depends_on` are `completed`, up to `concurrency_limit`; persist each step transition before scheduling the next; derive run outcome from success-vs-error of relevant steps only (cancelled/skipped do not flip it)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_
  - [x] 9.2 Write property test for dependency ordering and concurrency bound
    - **Property 6: Dependency ordering and concurrency bound**
    - **Validates: Requirements 3.2, 3.3, 3.4**
    - Use a `dags()` strategy with random topology and concurrency limit
  - [x] 9.3 Write property test for initial run state
    - **Property 7: Run state starts pending with a unique id**
    - **Validates: Requirements 3.1**
  - [x] 9.4 Write property test for run outcome derivation
    - **Property 8: Run outcome derives only from relevant success-vs-error**
    - **Validates: Requirements 3.5, 3.6**
  - [x] 9.5 Write property test for state persistence and restart survival
    - **Property 9: Step state persists and survives restart, including awaiting-approval**
    - **Validates: Requirements 3.7, 8.5**

- [x] 10. DAG_Executor cancellation, retry, and restart recovery (`core/dag_executor.py`)
  - [x] 10.1 Implement `cancel_run`, `retry_run`, and `resume_pending_runs`
    - Cancellation stops new scheduling and calls `infra.teardown` for in-flight workloads, reaching `cancelled` within 10s; retry re-runs the error closure (error steps + transitive dependents) preserving successful outputs; `resume_pending_runs` rebuilds in-flight and awaiting-approval runs from the DatabaseBackend at bootstrap
    - _Requirements: 4.2, 4.3, 4.4, 3.7, 8.5_
  - [x] 10.2 Write property test for cancellation behavior
    - **Property 11: Cancellation stops scheduling and tears down in-flight work**
    - **Validates: Requirements 4.2**
  - [x] 10.3 Write property test for retry closure
    - **Property 12: Retry re-executes exactly the error closure and preserves successes**
    - **Validates: Requirements 4.4**
  - [x] 10.4 Write example test for cancellation timing bound
    - Drive a mock clock and assert the run reaches `cancelled` within the 10s bound
    - _Requirements: 4.3_

- [x] 11. DAG_Executor agent integration (`core/dag_executor.py`)
  - [x] 11.1 Wire agent-step dispatch, upstream output flow, and failure recording
    - Dispatch agent steps via `Agent_Orchestrator`; pass completed upstream outputs as dependent inputs; on agent failure or pre-execution error set the step `failed` and record the reason; stop the run if a configured invocation does not execute or if invocation-event recording fails
    - _Requirements: 5.1, 5.2, 5.3, 5.5, 5.6_
  - [x] 11.2 Write property test for upstream output flow
    - **Property 13: Upstream outputs flow to dependents**
    - **Validates: Requirements 5.2**
  - [x] 11.3 Write property test for step-failure recording
    - **Property 14: Step failure marks the step failed and records the reason**
    - **Validates: Requirements 5.3**
  - [x] 11.4 Write property test for invocation/usage recording rules
    - **Property 15: Invocation and usage recording rules govern run continuation**
    - **Validates: Requirements 5.4, 5.6**
  - [x] 11.5 Write example tests for agent dispatch and run observation
    - Verify agent-step dispatch wiring (5.1) and the run observation API shape returning state, step states, and event history (4.5)
    - _Requirements: 5.1, 4.5_

- [x] 12. Approval_Manager (`core/approval_manager.py`)
  - [x] 12.1 Implement checkpoint pause/resume/reject and wire into the executor
    - `enter_checkpoint` sets the step `awaiting-approval`, pauses dependents, persists state (survives restart), and emits an `approval-required` event with context; `approve` resumes from the checkpoint; `reject` sets the run to terminal `rejected` and skips dependents
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_
  - [x] 12.2 Write property test for the approval lifecycle
    - **Property 23: Approval lifecycle pauses, resumes, and rejects correctly**
    - **Validates: Requirements 8.1, 8.2, 8.3, 8.4**

- [x] 13. Checkpoint - orchestration core
  - Ensure all tests pass, ask the user if questions arise.

- [x] 14. Provider_Router (`core/provider_router.py`)
  - [x] 14.1 Implement policy/preference selection and fallback ordering
    - `select` returns ordered provider/model candidates honoring the cost|speed|quality preference and configured fallback order, factoring provider health
    - _Requirements: 6.1, 6.3, 19.1_
  - [x] 14.2 Write property test for routing selection
    - **Property 16: Routing selects per policy and preference**
    - **Validates: Requirements 6.1, 19.1**

- [x] 15. Inference_Gateway call pipeline (`core/inference_gateway.py`)
  - [x] 15.1 Implement the `call` pipeline with retry, fallback, and exhaustion
    - Single entry point for model calls wrapping `ProviderService`; retry the selected provider with exponential backoff up to and including max retries, then advance the fallback order, then return an error naming all failed providers and record it in run history
    - _Requirements: 6.1, 6.2, 6.3, 6.4_
  - [x] 15.2 Write property test for bounded inclusive retry
    - **Property 17: Retry is bounded and inclusive of the configured maximum** — exactly `min(K+1, N+1)` attempts
    - **Validates: Requirements 6.2**
  - [x] 15.3 Write property test for ordered fallback and exhaustion
    - **Property 18: Fallback proceeds in order and reports exhaustion**
    - **Validates: Requirements 6.3, 6.4**

- [x] 16. Budgets and rate limits (`core/inference_gateway.py`)
  - [x] 16.1 Implement `BudgetTracker` and `RateLimiter` with status events
    - Track cumulative tokens/cost per run; block the first call that would exceed budget and transition the run to `budget_exceeded`; fail-open when budget state is unavailable (proceed, disable rate delays, record skip); bound calls per window and delay excess; emit status events on block/delay
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_
  - [x] 16.2 Write property test for budget tracking and blocking
    - **Property 20: Budget tracking is accurate and blocks on exceed**
    - **Validates: Requirements 7.1, 7.2**
  - [x] 16.3 Write property test for budget fail-open
    - **Property 21: Budget-state unavailability fails open and is recorded**
    - **Validates: Requirements 7.3**
  - [x] 16.4 Write property test for rate limiting and status events
    - **Property 22: Rate limiting bounds calls per window and emits status**
    - **Validates: Requirements 7.4, 7.5**
    - Drive with a mock clock

- [x] 17. Credential pools, prompt cache, and gateway wiring (`core/inference_gateway.py`)
  - [x] 17.1 Implement `CredentialPoolManager`, `PromptCache`, and kernel-grant integration
    - Obtain credentials only via kernel grants (cache only granted session context); rotate pool grants across successive calls and quarantine rejected grants; return cached responses on key match without a new provider call
    - _Requirements: 6.5, 19.2, 19.3, 19.4_
  - [x] 17.2 Write property test for no raw secrets in state
    - **Property 19: No raw secret values in Control_Plane state**
    - **Validates: Requirements 6.5, 18.4**
  - [x] 17.3 Write property test for credential pool rotation and rejection
    - **Property 42: Credential pool rotation and rejection handling**
    - **Validates: Requirements 19.2, 19.3**
  - [x] 17.4 Write property test for prompt cache hits
    - **Property 43: Prompt cache hits avoid provider calls**
    - **Validates: Requirements 19.4**
  - [x] 17.5 Wire the Inference_Gateway into `Agent_Orchestrator`/`agent_invoker`
    - Route existing agent invocations through `InferenceGateway.call` so all model calls pass policy/budget/cache; no orphaned direct provider calls remain
    - _Requirements: 6.1, 5.4_

- [x] 18. Checkpoint - inference layer
  - Ensure all tests pass, ask the user if questions arise.

- [x] 19. Tool_Registry (`core/tool_registry.py`)
  - [x] 19.1 Implement the tool/toolset catalog and scope gating
    - `register_tool`/`register_toolset`, `is_enabled`, and `invoke`; agent-level disable takes precedence over run-level enable; record denied invocations in run history; route mutating/command tools through the sandbox path
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_
  - [x] 19.2 Write property test for tool gating precedence and denial recording
    - **Property 24: Tool gating with agent-level precedence and recorded denials**
    - **Validates: Requirements 9.2, 9.3, 9.4**
    - Use a `tool_scopes()` strategy with random agent/run enable-disable maps
  - [x] 19.3 Write example test for the tool/toolset catalog
    - Verify catalog maintenance and grouping
    - _Requirements: 9.1_

- [x] 20. Code_Executor (`core/code_executor.py`)
  - [x] 20.1 Implement sandboxed script submission via RustInfra
    - Submit scripts only to a Kernel-managed Sandbox (never the host); return captured stdout/stderr/exit code; enforce a time limit by requesting workload termination and returning a timeout error; grant only the run's configured toolset and secret grants; block with no host fallback if routing fails
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 21.1, 21.2_
  - [x] 20.2 Write property test for mandatory sandbox routing
    - **Property 25: Mutating tools and submitted scripts always route through a Sandbox**
    - **Validates: Requirements 9.5, 16.1, 21.1**
  - [x] 20.3 Write property test for captured output passthrough
    - **Property 38: Code executor returns the captured sandbox output**
    - **Validates: Requirements 16.2**
  - [x] 20.4 Write property test for grant/toolset scoping
    - **Property 39: Sandboxes receive only the run's configured toolset and grants**
    - **Validates: Requirements 16.4**

- [x] 21. Skill_Manager (`core/skill_manager.py`)
  - [x] 21.1 Implement the skill catalog with progressive disclosure
    - Always contribute every skill's name + short description to context; load full body only when relevance is determined; parse agentskills.io documents; still load raw content when parsing fails due to corruption/encoding
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_
  - [x] 21.2 Write property test for progressive disclosure
    - **Property 26: Skill progressive disclosure**
    - **Validates: Requirements 10.2, 10.3**
    - Use a `skill_catalogs()` strategy
  - [x] 21.3 Write property test for skill document round-trip
    - **Property 27: Skill document round-trip**
    - **Validates: Requirements 10.4**
    - Use a `skill_documents()` strategy
  - [x] 21.4 Write example tests for catalog shape and corrupt-skill load
    - Verify catalog shape (10.1) and that a corrupt agentskills.io document still loads (10.5)
    - _Requirements: 10.1, 10.5_

- [x] 22. Memory_Store (`core/memory_store.py`)
  - [x] 22.1 Implement persistence, size-bound curation, deletion, and listing
    - Persist entries across sessions; enforce a configured max total size with curation (reject/remove) on overflow; remove on delete independent of a completion flag and return a descriptive error if deletion cannot complete; expose a list API
    - _Requirements: 11.1, 11.2, 11.3, 11.4_
  - [x] 22.2 Write property test for persistence and listing
    - **Property 28: Memory persistence and listing**
    - **Validates: Requirements 11.1, 11.4**
    - Use a `memory_entry_sequences()` strategy
  - [x] 22.3 Write property test for size-bound enforcement
    - **Property 29: Memory size bound is enforced**
    - **Validates: Requirements 11.2**
  - [x] 22.4 Write property test for deletion semantics
    - **Property 30: Memory deletion removes from persistence**
    - **Validates: Requirements 11.3**

- [x] 23. Context_Resolver (`core/context_resolver.py`)
  - [x] 23.1 Implement `@`-reference resolution, placeholders, and auto-discovery
    - Resolve file/folder/git-diff/URL references into concrete text via kernel-managed filesystem access and inject actual content; inject a descriptive placeholder for unresolvable references and continue processing the rest; auto-discover designated project context files on entering a project directory
    - _Requirements: 12.1, 12.2, 12.3, 12.4_
  - [x] 23.2 Write property test for reference resolution and graceful degradation
    - **Property 31: Context references resolve, inject actual content, and degrade gracefully**
    - **Validates: Requirements 12.1, 12.2, 12.3**
    - Use a `context_reference_sets()` strategy mixing resolvable/unresolvable refs
  - [x] 23.3 Write example test for project-file auto-discovery
    - _Requirements: 12.4_

- [x] 24. Checkpoint_Manager (`core/checkpoint_manager.py`)
  - [x] 24.1 Implement snapshot-before-mutation, restore, listing, and metadata-only storage
    - Request a kernel snapshot before any sandbox filesystem mutation; request restore on rollback; list checkpoints for a run; store only metadata/snapshot references (kernel owns contents); treat zero-checkpoint state as valid
    - _Requirements: 13.1, 13.2, 13.3, 13.4_
  - [x] 24.2 Write property test for snapshot/restore ordering
    - **Property 32: Snapshot precedes mutation and restore targets the chosen checkpoint**
    - **Validates: Requirements 13.1, 13.2**
  - [x] 24.3 Write property test for kernel-owned checkpoint contents
    - **Property 33: Kernel owns checkpoint contents; Control_Plane stores only references**
    - **Validates: Requirements 13.4**
  - [x] 24.4 Write example test for checkpoint listing API
    - _Requirements: 13.3_

- [x] 25. Scheduler (`core/scheduler.py`)
  - [x] 25.1 Implement task persistence, trigger loop, and invalid-expression rejection
    - Persist Workflow_Definition↔schedule associations in active or paused state; start a run when the clock matches an active task; never trigger a paused task; reject invalid schedule expressions with a descriptive error; uses `Cron_Parser` and calls `DagExecutor.start_run`
    - _Requirements: 14.1, 14.2, 14.3, 14.5_
  - [x] 25.2 Write property test for scheduled-task persistence and triggering
    - **Property 34: Scheduled tasks persist and trigger only when active**
    - **Validates: Requirements 14.1, 14.2, 14.3**
    - Drive with a mock clock
  - [x] 25.3 Write property test for invalid-schedule rejection
    - **Property 36: Invalid schedule expressions are rejected descriptively**
    - **Validates: Requirements 14.5**

- [x] 26. Subagent_Manager (`core/subagent_manager.py`)
  - [x] 26.1 Implement isolated spawn, toolset restriction, concurrency queue, and accounting
    - Spawn subagents with isolated context; restrict each to the toolset granted at spawn; queue requests beyond the concurrency limit; on completion return the result to the parent and record token usage against the run
    - _Requirements: 15.1, 15.2, 15.3, 15.4_
  - [x] 26.2 Write property test for subagent isolation and bounds
    - **Property 37: Subagent isolation, toolset restriction, concurrency bound, and accounting**
    - **Validates: Requirements 15.1, 15.2, 15.3, 15.4**

- [x] 27. Hook_Manager (`core/hook_manager.py`)
  - [x] 27.1 Implement hook registration, execution, failure isolation, and guardrails
    - Register hooks against lifecycle events; run them with event context; let non-blocking hooks not block the run; record hook errors and continue unless the hook is a blocking guardrail; stop the associated step when a blocking guardrail denies the action
    - _Requirements: 17.1, 17.2, 17.3, 17.4_
  - [x] 27.2 Write property test for hook execution and guardrails
    - **Property 40: Event hooks run, isolate failures, and enforce guardrails**
    - **Validates: Requirements 17.2, 17.3, 17.4**
  - [x] 27.3 Write example test for hook registration
    - _Requirements: 17.1_

- [x] 28. MCP_Client (`core/mcp_client.py`)
  - [x] 28.1 Implement connection, filtered tool registration, disconnect handling, and grant-only credentials
    - Connect over the configured transport and register server tools into the Tool_Registry; apply per-server tool filters; mark tools unavailable and record disconnection when unreachable; obtain credentials only via kernel grants and fail the connection rather than fall back to raw CP secrets
    - _Requirements: 18.1, 18.2, 18.3, 18.4, 18.5_
  - [x] 28.2 Write property test for filtered tool registration
    - **Property 41: MCP tool registration honors the per-server filter** — registered tools equal advertised ∩ filter
    - **Validates: Requirements 18.2**
  - [x] 28.3 Write integration tests for MCP connection lifecycle
    - Mocked-server connect + tool registration (18.1), disconnect marks tools unavailable (18.3), and no-grant connection fails without raw-secret fallback (18.5)
    - _Requirements: 18.1, 18.3, 18.5_

- [x] 29. Checkpoint - capability subsystems
  - Ensure all tests pass, ask the user if questions arise.

- [x] 30. API and WebSocket layer (`cp/`)
  - [x] 30.1 Implement the WebSocket server and connect Event_Router push
    - Add `cp/ws_server.py` running alongside `HttpShellServer`; stream normalized workflow events (step transitions, approvals, budget/rate status) to the Frontend
    - _Requirements: 4.1, 7.5, 8.2, 20.4_
  - [x] 30.2 Implement `cp/handlers/workflows.py`
    - Create/validate (persist only on successful `build_dag`), start/observe/cancel/retry runs, and a reusable workflow template catalog
    - _Requirements: 1.4, 4.5, 4.2, 4.4, 20.1, 20.2_
  - [x] 30.3 Implement `cp/handlers/schedules.py`
    - Create/pause/resume/list scheduled tasks
    - _Requirements: 14.1, 14.3_
  - [x] 30.4 Implement `cp/handlers/memory.py`
    - List/create/delete memory entries
    - _Requirements: 11.4, 11.1, 11.3_
  - [x] 30.5 Implement `cp/handlers/checkpoints.py`
    - List checkpoints for a run and request rollback
    - _Requirements: 13.3, 13.2_
  - [x] 30.6 Implement `cp/handlers/tools.py`
    - List/enable/disable tools and toolsets per scope
    - _Requirements: 9.1, 9.2_
  - [x] 30.7 Implement `cp/handlers/mcp.py`
    - Configure/list MCP server connections
    - _Requirements: 18.1_
  - [x] 30.8 Implement non-technical error presentation in `cp/http_responders.py`
    - Map internal exceptions to non-technical messages and strip stack traces from user-facing responses (retain secret-redacted detail in server logs)
    - _Requirements: 20.3_
  - [x] 30.9 Write property test for user-facing error messages
    - **Property 44: User-facing errors carry no raw stack traces**
    - **Validates: Requirements 20.3**
  - [x] 30.10 Register handlers and wire subsystems in bootstrap
    - Register new handlers via `cp/handlers/router.py`, construct and inject all subsystems in `cp/bootstrap.py`, and call `DagExecutor.resume_pending_runs()` at startup
    - _Requirements: 3.7, 8.5, 20.1_
  - [x] 30.11 Write integration test for WebSocket delivery and templates
    - End-to-end WebSocket event delivery and template catalog instantiation
    - _Requirements: 4.1, 20.1, 20.2_

- [x] 31. Frontend views (`src/`)
  - [x] 31.1 Implement the workflow view (create/edit/run/observe/cancel/retry)
    - Drive entirely via Control_Plane HTTP + WebSocket APIs; render run/step state from streamed events
    - _Requirements: 20.1, 20.4, 4.1_
  - [x] 31.2 Implement the approvals view
    - Surface approval-required events and submit approve/reject decisions
    - _Requirements: 20.4, 8.2_
  - [x] 31.3 Implement the budgets view
    - Display budget usage and budget/rate status events
    - _Requirements: 20.4, 7.5_
  - [x] 31.4 Implement the checkpoints view
    - List checkpoints and trigger rollback
    - _Requirements: 20.4, 13.3_
  - [x] 31.5 Implement the schedule view
    - Create/pause/resume scheduled tasks
    - _Requirements: 20.4, 14.1_
  - [x] 31.6 Write frontend smoke test for CP-only API consumption
    - Assert views call only Control_Plane HTTP/WebSocket endpoints
    - _Requirements: 20.4_

- [x] 32. End-to-end and scope-boundary tests
  - [x] 32.1 Write integration smoke test for the kernel-backed sandbox exec path
    - Exercise a sandbox exec round-trip through `RustInfraExecutionManager` (mocked or local kernel)
    - _Requirements: 16.1, 16.2, 21.1_
  - [x] 32.2 Write smoke test for scope boundaries
    - Assert out-of-scope features (voice, vision, browser automation, Kubernetes, distributed swarm) are absent and no host execution path exists
    - _Requirements: 21.3, 21.1_

- [x] 33. Final checkpoint
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional test sub-tasks and can be skipped for a faster MVP; core implementation tasks are never optional.
- Each property test is implemented with Hypothesis (min 100 examples), lives in its own file under `control-plane/tests/`, and carries the tag `# Feature: orchestration-engine-completion, Property N: ...`.
- Kernel, providers, MCP servers, and the system clock are mocked in property tests; the new kernel gRPC surface (sandbox Exec, FS Snapshot/Restore, Secret Grant) is consumed only through `RustInfraExecutionManager`.
- Each task references specific requirement clauses and/or design properties for traceability.
- Checkpoints provide incremental validation at layer boundaries.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.3"] },
    { "id": 1, "tasks": ["1.2", "2.1", "3.1", "5.1", "7.1", "8.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "3.2", "4.1", "5.2", "7.2", "8.2", "8.3", "8.4", "14.1", "19.1", "21.1", "22.1", "23.1"] },
    { "id": 3, "tasks": ["4.2", "4.3", "4.4", "7.3", "9.1", "14.2", "15.1", "19.2", "19.3", "20.1", "21.2", "21.3", "21.4", "22.2", "22.3", "22.4", "23.2", "23.3", "24.1", "26.1", "28.1"] },
    { "id": 4, "tasks": ["7.4", "9.2", "9.3", "9.4", "9.5", "10.1", "15.2", "15.3", "16.1", "20.2", "20.3", "20.4", "24.2", "24.3", "24.4", "25.1", "26.2", "28.2", "28.3"] },
    { "id": 5, "tasks": ["10.2", "10.3", "10.4", "11.1", "16.2", "16.3", "16.4", "17.1", "25.2", "25.3", "27.1"] },
    { "id": 6, "tasks": ["11.2", "11.3", "11.4", "11.5", "12.1", "17.2", "17.3", "17.4", "17.5", "27.2", "27.3"] },
    { "id": 7, "tasks": ["12.2", "30.1", "30.2", "30.3", "30.4", "30.5", "30.6", "30.7", "30.8"] },
    { "id": 8, "tasks": ["30.9", "30.10"] },
    { "id": 9, "tasks": ["30.11", "31.1", "31.2", "31.3", "31.4", "31.5"] },
    { "id": 10, "tasks": ["31.6", "32.1", "32.2"] }
  ]
}
```
