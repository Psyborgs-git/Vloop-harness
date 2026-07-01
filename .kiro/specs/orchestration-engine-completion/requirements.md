# Requirements Document

## Introduction

VLoop is a cross-platform, local-first AI orchestration platform split between a Rust infrastructure daemon (`vloopd`, the resource authority) and a Python Control Plane (the cognitive authority that owns orchestration, inference, workflow state, windows, and the user-facing API). The React frontend talks only to Control Plane HTTP/WebSocket APIs.

This feature completes the planned orchestration engine (build roadmap Stage 6: planner/DAG engine, multi-agent orchestration, inference gateway policy, approvals, event routing) and selectively extends it with the highest-value capabilities inspired by Hermes Agent (Nous Research) that fit a **non-technical, local-first, sandboxed, secret-safe desktop product**: reusable tools/toolsets, on-demand skills, bounded persistent memory, context references, checkpoints/rollback, scheduled tasks, bounded subagent delegation, sandboxed code execution, lifecycle event hooks, MCP integration, and provider routing/fallback for reliability and cost control.

The feature MUST respect existing architecture boundaries: the Control Plane decides WHAT happens; the Kernel decides HOW and WHERE it runs. All code execution and file mutation happen only inside Kernel-managed sandboxes, secrets are injected by capability and never returned raw to the Control Plane, and the frontend reaches infrastructure only through Control Plane APIs.

This document defines functional and quality requirements. Implementation choices (libraries, schemas, internal data structures) are deferred to the design phase.

## Glossary

- **Control_Plane**: The Python cognitive authority that owns orchestration, inference policy, workflow state, the HTTP/WebSocket API, and window lifecycle. The "system" in most requirements below is a named Control_Plane subsystem.
- **Kernel**: The Rust daemon (`vloopd`) that owns workloads, filesystem, network, secrets, databases, dependencies, and supervision. Reached only over local IPC (gRPC).
- **Frontend**: The React + TypeScript application served by the Control_Plane, communicating only via Control_Plane HTTP/WebSocket APIs.
- **Workflow**: A user-defined unit of automation consisting of an objective, an execution graph of steps, configuration, and runtime state.
- **Workflow_Definition**: The persisted, serializable description of a Workflow (steps, edges, inputs, policies) independent of any single run.
- **Workflow_Run**: A single execution instance of a Workflow_Definition, with its own state, events, and artifacts.
- **Workflow_Step**: A single node in a Workflow graph (for example, an agent invocation, a tool call, an approval checkpoint, or a subworkflow).
- **DAG**: A directed acyclic graph of Workflow_Steps and their dependency edges.
- **Planner**: The Control_Plane subsystem that builds and validates a DAG from a Workflow_Definition.
- **DAG_Executor**: The Control_Plane subsystem that executes a validated DAG, scheduling steps according to dependency edges and concurrency limits.
- **Agent_Orchestrator**: The existing Control_Plane subsystem that manages agents and dispatches agent invocations (extended by this feature).
- **Inference_Gateway**: The Control_Plane subsystem that centralizes provider selection, model profiles, budgets, rate limits, retries, fallbacks, and routing for all model calls.
- **Provider_Router**: The component of the Inference_Gateway that selects a provider/model for a request based on a routing policy and provider health.
- **Budget**: A configured maximum spend or token allowance for a scope (Workflow_Run, Workflow_Definition, or global), measured in tokens or estimated cost.
- **Rate_Limit**: A configured maximum number of requests or tokens per time window for a provider or scope.
- **Credential_Pool**: A named set of interchangeable secret references for one provider, used for rotation and parallelism, managed via Kernel secret grants.
- **Prompt_Cache**: A Control_Plane cache of prior model responses keyed by request content used to avoid redundant provider calls.
- **Approval_Manager**: The Control_Plane subsystem that pauses a Workflow_Run at an Approval_Checkpoint and resumes it on user decision.
- **Approval_Checkpoint**: A Workflow_Step that requires explicit user approval, rejection, or edit before execution continues.
- **Event_Router**: The Control_Plane subsystem that converts Kernel events and internal orchestration events into user-facing workflow state and streams them to the Frontend.
- **Tool**: A named, schema-described function an agent can call (for example, web search, file edit, run command).
- **Toolset**: A named, enable/disable-able group of Tools.
- **Tool_Registry**: The Control_Plane subsystem that catalogs Tools and Toolsets and enforces which are available to a given agent or Workflow_Run.
- **Skill**: An on-demand knowledge document loaded into agent context only when relevant, following progressive disclosure.
- **Skill_Manager**: The Control_Plane subsystem that catalogs Skills and decides when to load Skill content into context.
- **Memory_Store**: The Control_Plane subsystem that persists bounded, curated, cross-session memory entries (preferences, projects, environment facts).
- **Memory_Entry**: A single curated fact or note in the Memory_Store.
- **Context_Resolver**: The Control_Plane subsystem that resolves Context_References into concrete text injected into agent context.
- **Context_Reference**: An inline `@`-prefixed token referring to a file, folder, git diff, or URL to be injected into context.
- **Checkpoint_Manager**: The Control_Plane subsystem that requests a Kernel snapshot of a sandbox workspace before file mutations and requests rollback on demand.
- **Checkpoint**: A point-in-time snapshot of a sandbox workspace, owned and stored by the Kernel.
- **Scheduler**: The Control_Plane subsystem that triggers Workflow_Runs on a time schedule.
- **Scheduled_Task**: A persisted association of a Workflow_Definition with a schedule (cron expression or natural-language-derived schedule).
- **Cron_Parser**: The Control_Plane component that parses and formats cron schedule expressions.
- **Subagent_Manager**: The Control_Plane subsystem that spawns child agents with isolated context and restricted Toolsets under a concurrency limit.
- **Subagent**: A child agent invocation spawned by a parent agent or Workflow_Step with its own isolated context.
- **Code_Executor**: The Control_Plane subsystem that submits agent-authored scripts to the Kernel for sandboxed execution and returns results.
- **Sandbox**: A Kernel-managed isolated execution environment (a workload) in which code and tools run; no host execution occurs.
- **Hook_Manager**: The Control_Plane subsystem that runs configured Event_Hooks at defined lifecycle points.
- **Event_Hook**: A user- or template-configured action (for example, a webhook call, a log entry, or a guardrail check) bound to a lifecycle event.
- **MCP**: Model Context Protocol, an open standard for connecting to external tool servers.
- **MCP_Client**: The Control_Plane subsystem that connects to MCP servers and exposes their tools through the Tool_Registry with per-server filtering.
- **Workflow_Serializer**: The Control_Plane component that serializes a Workflow_Definition to a storage format and deserializes it back.

## Requirements

### Requirement 1: Workflow Definition and Validation

**User Story:** As a non-technical professional, I want to define a multi-step automation as a workflow, so that I can describe what I want done without writing code.

#### Acceptance Criteria

1. WHEN a user submits a Workflow_Definition through the Control_Plane API, THE Planner SHALL build a DAG of Workflow_Steps and dependency edges from the definition.
2. IF a submitted Workflow_Definition contains a cycle in its dependency edges, THEN THE Planner SHALL reject the definition, return an error identifying the steps involved in the cycle, and THE Control_Plane SHALL leave the rejected definition unpersisted and without an assigned unique identifier.
3. IF a Workflow_Step references an agent, tool, or input that does not exist, THEN THE Planner SHALL reject the definition, return an error naming the missing reference, and THE Control_Plane SHALL leave the rejected definition unpersisted and without an assigned unique identifier.
4. WHEN a Workflow_Definition passes validation, THE Control_Plane SHALL persist the Workflow_Definition with a unique identifier, and THE Control_Plane SHALL assign a unique identifier only to definitions that pass validation.
5. THE Planner SHALL validate a Workflow_Definition without dispatching any model call or Kernel workload.

### Requirement 2: Workflow Definition Serialization (Round-Trip)

**User Story:** As a professional, I want my workflows saved and reloaded exactly as I built them, so that I can reuse and share them reliably.

#### Acceptance Criteria

1. THE Workflow_Serializer SHALL serialize any valid Workflow_Definition into a persisted storage format.
2. THE Workflow_Serializer SHALL deserialize a persisted Workflow_Definition into an equivalent in-memory Workflow_Definition.
3. FOR ALL valid Workflow_Definitions, serializing then deserializing then serializing SHALL produce output equal to the first serialization (round-trip property).
4. IF the Workflow_Serializer is given malformed serialized input, THEN THE Workflow_Serializer SHALL return a descriptive error and SHALL NOT raise an unhandled exception.

### Requirement 3: Workflow Execution and DAG Scheduling

**User Story:** As a professional, I want to run a workflow and have its steps execute in the right order, so that the automation completes correctly.

#### Acceptance Criteria

1. WHEN a user starts a Workflow_Run from a validated Workflow_Definition, THE DAG_Executor SHALL create a Workflow_Run with a unique identifier and an initial state of pending.
2. THE DAG_Executor SHALL execute a Workflow_Step only after all of the steps it depends on have reached a completed state, and WHILE any step a Workflow_Step depends on has not reached a completed state, THE DAG_Executor SHALL prevent that Workflow_Step from beginning execution.
3. WHEN all of the steps a Workflow_Step depends on have reached a completed state, THE DAG_Executor SHALL schedule that Workflow_Step for execution subject to the configured concurrency limit.
4. WHERE two or more Workflow_Steps have no dependency path between them, THE DAG_Executor SHALL be permitted to execute those steps concurrently up to the configured concurrency limit.
5. WHEN every Workflow_Step in a Workflow_Run reaches a terminal state, THE DAG_Executor SHALL set the Workflow_Run state to completed if all relevant steps succeeded, or failed if any relevant step ended in error.
6. WHERE a Workflow_Step reaches a terminal state that is neither success nor error, such as cancelled or skipped, THE DAG_Executor SHALL leave the Workflow_Run completed-versus-failed determination unchanged by that step, so that only success-versus-error among the relevant steps drives the completed or failed outcome.
7. WHILE a Workflow_Run is executing, THE Control_Plane SHALL persist the state of each Workflow_Step so that run state survives a Control_Plane restart.

### Requirement 4: Workflow Observation, Cancellation, and Retry

**User Story:** As a professional, I want to watch a running workflow and stop or retry it, so that I stay in control of automations.

#### Acceptance Criteria

1. WHILE a Workflow_Run is executing, THE Event_Router SHALL stream Workflow_Step state transitions to the Frontend over the WebSocket API.
2. WHEN a user requests cancellation of a Workflow_Run, THE DAG_Executor SHALL stop scheduling new Workflow_Steps and SHALL request teardown of any in-flight Kernel workloads for that run.
3. WHEN a Workflow_Run cancellation completes, THE DAG_Executor SHALL set the Workflow_Run state to cancelled within 10 seconds of the cancellation request.
4. WHEN a user requests retry of a failed Workflow_Run, THE DAG_Executor SHALL re-execute the steps that ended in error and the steps that depend on them, while preserving the results of steps that already completed successfully.
5. THE Control_Plane SHALL expose an API that returns the current state, step states, and event history of a Workflow_Run.

### Requirement 5: Multi-Agent Orchestration

**User Story:** As a professional, I want a workflow to coordinate several agents, so that specialized agents handle different parts of a task.

#### Acceptance Criteria

1. WHERE a Workflow_Step is configured as an agent invocation, THE Agent_Orchestrator SHALL dispatch the invocation using the agent configuration referenced by the step.
2. WHEN an upstream Workflow_Step completes, THE DAG_Executor SHALL make the upstream step output available as input to its dependent Workflow_Steps.
3. IF an agent invocation within a Workflow_Step fails, or IF a Workflow_Step encounters a pre-execution error before its agent invocation begins, THEN THE DAG_Executor SHALL set that step state to failed and SHALL record the failure reason in the Workflow_Run event history.
4. WHEN an agent invocation executes within a Workflow_Run, THE Agent_Orchestrator SHALL record an invocation event, and WHERE token usage is available, THE Agent_Orchestrator SHALL record token usage; IF token usage recording fails, THEN THE Agent_Orchestrator SHALL continue the Workflow_Run provided the invocation event was recorded.
5. IF a configured agent invocation within a Workflow_Step does not execute at all, THEN THE DAG_Executor SHALL stop the Workflow_Run.
6. IF recording the invocation event for an agent invocation fails, THEN THE Agent_Orchestrator SHALL stop the entire Workflow_Run.

### Requirement 6: Inference Gateway Routing and Fallback

**User Story:** As a professional, I want the system to choose a working model provider automatically and fail over when one is down, so that my automations keep running reliably.

#### Acceptance Criteria

1. WHEN an agent or Workflow_Step issues a model call, THE Inference_Gateway SHALL select the provider and model according to the configured routing policy for that scope.
2. IF a selected provider returns a retryable error and the number of retry attempts already performed is less than the configured maximum retry count, THEN THE Inference_Gateway SHALL retry the call using exponential backoff, such that the call is retried up to and including the configured maximum retry count (inclusive).
3. IF a selected provider remains unavailable after the configured maximum retry count, THEN THE Provider_Router SHALL route the call to the next provider in the configured fallback order.
4. IF all providers in the fallback order are exhausted, THEN THE Inference_Gateway SHALL return an error identifying the failed providers and SHALL record the failure in the Workflow_Run event history.
5. THE Inference_Gateway SHALL obtain provider credentials through a Kernel secret grant and SHALL NOT read raw secret values into Control_Plane application state; WHERE an in-memory credential cache is used for performance, THE Inference_Gateway SHALL store only the granted session context and SHALL NOT store raw secret values.

### Requirement 7: Budgets and Rate Limits

**User Story:** As a professional, I want to cap how much a workflow can spend, so that automations do not run up unexpected costs.

#### Acceptance Criteria

1. THE Inference_Gateway SHALL track cumulative token usage and estimated cost per Workflow_Run against the configured Budget for that scope.
2. IF executing a model call would cause a Workflow_Run to exceed its configured Budget, THEN THE Inference_Gateway SHALL block the call and SHALL set the Workflow_Run state to a budget-exceeded terminal state.
3. IF the Budget check cannot be performed because budget state is temporarily unavailable, THEN THE Inference_Gateway SHALL allow the model call to proceed, SHALL disable Rate_Limit delays for that call, and SHALL record the skipped Budget check in the Workflow_Run event history.
4. WHILE the number of model calls in the current time window has reached the configured Rate_Limit for a provider, THE Inference_Gateway SHALL delay further calls to that provider until the window allows them.
5. WHEN a Workflow_Run is blocked by a Budget or delayed by a Rate_Limit, THE Event_Router SHALL stream a corresponding status event to the Frontend.

### Requirement 8: Approval Checkpoints

**User Story:** As a professional, I want to approve sensitive actions before they run, so that I can prevent unwanted changes.

#### Acceptance Criteria

1. WHEN a Workflow_Run reaches an Approval_Checkpoint, THE Approval_Manager SHALL pause execution of that step and its dependents and SHALL set the step state to awaiting-approval.
2. WHEN a Workflow_Run reaches an Approval_Checkpoint, THE Event_Router SHALL stream an approval-required event containing the checkpoint context to the Frontend.
3. WHEN a user approves an Approval_Checkpoint, THE Approval_Manager SHALL resume execution from that checkpoint.
4. WHEN a user rejects an Approval_Checkpoint, THE Approval_Manager SHALL set the Workflow_Run to a terminal rejected state and SHALL NOT execute the steps that depend on the checkpoint.
5. WHILE a Workflow_Run is awaiting approval, THE Control_Plane SHALL preserve the Workflow_Run state so that a pending approval survives a Control_Plane restart.

### Requirement 9: Tools and Toolsets

**User Story:** As a professional, I want to turn capabilities like web search or file editing on or off for an agent, so that agents only do what I allow.

#### Acceptance Criteria

1. THE Tool_Registry SHALL maintain a catalog of available Tools and the Toolsets that group them.
2. WHERE a Toolset is disabled for an agent or Workflow_Run, THE Tool_Registry SHALL prevent the Tools in that Toolset from being invoked in that scope.
3. WHERE a Toolset is disabled at the agent level, THE Tool_Registry SHALL block its Tools even if the same Toolset is enabled at the Workflow_Run level, so that agent-level restrictions take precedence.
4. WHEN an agent attempts to invoke a Tool that is not enabled in its current scope, THE Tool_Registry SHALL deny the invocation and SHALL record the denial in the Workflow_Run event history.
5. WHERE a Tool performs filesystem mutation or command execution, THE Control_Plane SHALL route that Tool's execution through a Kernel-managed Sandbox.

### Requirement 10: Skills with Progressive Disclosure

**User Story:** As a professional, I want agents to use reference knowledge only when relevant, so that responses stay accurate without wasting tokens.

#### Acceptance Criteria

1. THE Skill_Manager SHALL maintain a catalog of Skills, each with a name, a short description, and a body of knowledge content.
2. WHEN building agent context, THE Skill_Manager SHALL include the name and short description of each catalogued Skill regardless of relevance.
3. WHEN a Skill is determined relevant to the current task, THE Skill_Manager SHALL load that Skill's full body content into agent context while retaining the Skill's name and short description.
4. THE Skill_Manager SHALL parse Skill documents that conform to the agentskills.io open standard format.
5. IF a Skill document that conforms to the agentskills.io open standard fails to parse due to corruption or encoding issues, THEN THE Skill_Manager SHALL still load that Skill's content.

### Requirement 11: Persistent Bounded Memory

**User Story:** As a professional, I want the system to remember my preferences and project facts across sessions, so that I do not repeat myself.

#### Acceptance Criteria

1. WHEN a user or an agent records a Memory_Entry, THE Memory_Store SHALL persist the entry so that it is available in later sessions.
2. THE Memory_Store SHALL enforce a configured maximum total size, and IF adding a Memory_Entry would exceed the maximum size, THEN THE Memory_Store SHALL require curation before the entry is stored, and THE Memory_Store SHALL be permitted to reject or remove entries during curation.
3. WHEN a user requests deletion of a Memory_Entry, THE Memory_Store SHALL remove that entry from persistence independently of any deletion completion status, so that removal is not coupled to a completion flag, and IF the deletion cannot be completed, THEN THE Memory_Store SHALL return a descriptive error to the user.
4. THE Control_Plane SHALL expose an API that lists all current Memory_Entries for user review.

### Requirement 12: Context Files and Context References

**User Story:** As a professional, I want to point an agent at a file, folder, or link inline, so that it works with the right material.

#### Acceptance Criteria

1. WHEN an agent input contains a Context_Reference, THE Context_Resolver SHALL resolve the reference into concrete text and inject that text into the agent context.
2. WHERE a Context_Reference points to a file or folder, THE Context_Resolver SHALL read the referenced content through Kernel-managed filesystem access and SHALL inject the actual content into the agent context when access succeeds.
3. IF a Context_Reference cannot be resolved, THEN THE Context_Resolver SHALL inject a descriptive placeholder identifying the unresolved reference and SHALL continue processing remaining references.
4. WHEN the Control_Plane starts working in a project directory, THE Context_Resolver SHALL auto-discover designated project context files in that directory.

### Requirement 13: Checkpoints and Rollback

**User Story:** As a professional, I want the system to snapshot my files before it changes them, so that I can undo mistakes safely.

#### Acceptance Criteria

1. WHEN a Workflow_Step is about to perform filesystem mutation in a Sandbox, THE Checkpoint_Manager SHALL request a Kernel snapshot of the affected workspace before the mutation occurs.
2. WHEN a user requests rollback to a Checkpoint, THE Checkpoint_Manager SHALL request that the Kernel restore the workspace to that Checkpoint's state.
3. THE Control_Plane SHALL expose an API that lists the Checkpoints available for a Workflow_Run.
4. THE Checkpoint_Manager SHALL treat the Kernel as the owner of Checkpoint storage even when no Checkpoints exist yet, SHALL rely on the Kernel to persist Checkpoint snapshot contents, SHALL treat a configuration with zero Checkpoints and no snapshot contents as valid, and SHALL NOT store snapshot file contents in Control_Plane state.

### Requirement 14: Scheduled Tasks

**User Story:** As a professional, I want to schedule a workflow to run automatically, so that routine work happens without me starting it.

#### Acceptance Criteria

1. WHEN a user creates a Scheduled_Task, THE Scheduler SHALL persist the association of a Workflow_Definition with its schedule, and THE Scheduler SHALL allow the Scheduled_Task to be created in either an active or a paused state.
2. WHEN the current time matches a Scheduled_Task's schedule, THE Scheduler SHALL start a Workflow_Run for the associated Workflow_Definition.
3. WHEN a user pauses a Scheduled_Task, THE Scheduler SHALL stop starting new Workflow_Runs for that task until it is resumed.
4. THE Cron_Parser SHALL parse a cron expression into a schedule and SHALL format a schedule back into a cron expression, such that for all valid cron expressions, parsing then formatting then parsing produces an equivalent schedule (round-trip property).
5. IF a user submits an invalid schedule expression, THEN THE Scheduler SHALL reject the Scheduled_Task and return a descriptive error.

### Requirement 15: Subagent Delegation

**User Story:** As a professional, I want a complex task to delegate parts to focused helper agents, so that large jobs are handled reliably without losing focus.

#### Acceptance Criteria

1. WHEN a Workflow_Step or agent requests delegation, THE Subagent_Manager SHALL spawn a Subagent with an isolated context separate from its parent.
2. THE Subagent_Manager SHALL restrict each Subagent to the Toolset granted at spawn time.
3. WHILE the number of active Subagents has reached the configured concurrency limit, THE Subagent_Manager SHALL queue additional Subagent requests until an active Subagent completes.
4. WHEN a Subagent completes, THE Subagent_Manager SHALL return the Subagent result to the parent and SHALL record the Subagent's token usage against the Workflow_Run.

### Requirement 16: Sandboxed Code Execution

**User Story:** As a professional, I want agents to run scripts safely, so that multi-step work completes without risking my computer.

#### Acceptance Criteria

1. WHEN an agent submits a script for execution, THE Code_Executor SHALL submit the script to a Kernel-managed Sandbox and SHALL NOT execute the script on the host.
2. WHEN a Sandbox produces output, THE Code_Executor SHALL return the captured stdout, stderr, and exit code to the requesting agent.
3. IF a script exceeds the configured execution time limit, THEN THE Code_Executor SHALL request termination of the Sandbox workload and SHALL return a timeout error.
4. THE Code_Executor SHALL grant a Sandbox only the Toolset and secret grants configured for the enclosing Workflow_Run.

### Requirement 17: Event Hooks

**User Story:** As a professional, I want custom actions to fire at key moments, so that I can integrate notifications and guardrails.

#### Acceptance Criteria

1. THE Hook_Manager SHALL allow Event_Hooks to be registered against defined lifecycle events of a Workflow_Run.
2. WHEN a lifecycle event with a registered Event_Hook occurs, THE Hook_Manager SHALL run the registered Event_Hook with the event context, and WHERE the Event_Hook is non-blocking, THE Hook_Manager SHALL allow the Workflow_Run to continue without waiting for the Event_Hook to complete.
3. IF an Event_Hook raises an error or fails to execute due to a system condition, THEN THE Hook_Manager SHALL record the error in the Workflow_Run event history and SHALL continue executing the Workflow_Run unless the Event_Hook is configured as a blocking guardrail.
4. WHERE an Event_Hook is configured as a blocking guardrail and the guardrail denies the action, THE Hook_Manager SHALL stop the associated Workflow_Step from proceeding.

### Requirement 18: MCP Server Integration

**User Story:** As a professional, I want to connect external tool servers, so that I can extend what agents can do without custom development.

#### Acceptance Criteria

1. WHEN a user configures an MCP server connection, THE MCP_Client SHALL connect to the server over the configured transport and SHALL register the server's tools in the Tool_Registry.
2. WHERE a per-server tool filter is configured, THE MCP_Client SHALL register only the tools permitted by that filter.
3. IF an MCP server becomes unreachable, THEN THE MCP_Client SHALL mark its registered tools unavailable in the Tool_Registry and SHALL record the disconnection in the event history.
4. THE MCP_Client SHALL obtain any MCP server credentials through a Kernel secret grant rather than from raw secret values held in Control_Plane state.
5. IF neither a Kernel secret grant nor any other configured source provides the required MCP server credentials, THEN THE MCP_Client SHALL allow the connection to fail and SHALL NOT fall back to raw Control_Plane secret values.

### Requirement 19: Provider Routing, Credential Pools, and Prompt Caching

**User Story:** As a professional, I want the system to route model calls for cost and speed, rotate keys, and avoid redundant calls, so that automations are economical and fast.

#### Acceptance Criteria

1. WHERE a routing policy specifies an optimization preference of cost, speed, or quality, THE Provider_Router SHALL select among eligible providers according to that preference.
2. WHERE a Credential_Pool is configured for a provider, THE Inference_Gateway SHALL rotate across the pool's secret grants for successive calls.
3. IF a secret grant in a Credential_Pool is rejected by the provider as invalid, THEN THE Inference_Gateway SHALL select another grant from the pool and SHALL record the rejected grant for review.
4. WHERE Prompt_Cache is enabled and an incoming request matches a cached response key, THE Inference_Gateway SHALL return the cached response without issuing a new provider call.

### Requirement 20: Guided Non-Technical User Experience

**User Story:** As a non-technical professional, I want to build and run workflows through guided screens, so that I never need a terminal or to write code.

#### Acceptance Criteria

1. THE Control_Plane SHALL expose APIs that allow the Frontend to create, edit, run, observe, cancel, and retry Workflows without requiring command-line interaction.
2. THE Control_Plane SHALL provide a catalog of reusable Workflow templates that a user can instantiate.
3. WHEN a user action fails, THE Control_Plane SHALL return an error message that states the cause in non-technical language and SHALL avoid exposing raw stack traces in the user-facing message.
4. THE Frontend SHALL surface workflow run state, approvals, budgets, and checkpoints through dedicated views driven only by Control_Plane HTTP/WebSocket APIs.

### Requirement 21: Scope Boundaries and Safety Invariants

**User Story:** As a stakeholder, I want the feature's scope and safety guarantees defined, so that the build stays focused and secure.

#### Acceptance Criteria

1. THE Control_Plane SHALL route all code execution and filesystem mutation through Kernel-managed Sandboxes regardless of the execution path type, and no host execution path SHALL be provided, so that no non-host execution path bypasses a Sandbox.
2. IF routing an execution to a Kernel-managed Sandbox fails, THEN THE Control_Plane SHALL block the execution completely and SHALL NOT fall back to a host execution path.
3. THE Control_Plane SHALL keep voice mode, vision and image input, browser automation, Kubernetes backends, and distributed swarm execution out of scope for this feature.
4. THE Control_Plane SHALL redact secret values from all logs, events, and Frontend-facing responses.
5. WHEN any orchestration subsystem records an event, THE Control_Plane SHALL include the associated Workflow_Run identifier so that events are auditable per run.
