# Requirements Document

## Introduction

This feature completes the VLoop Control Plane into a full, configurable AI agent orchestration engine targeted at non-technical professionals. It delivers the real workflow engine described in Stage 6 of the build roadmap: a planner/DAG engine, multi-agent orchestration, an inference gateway with budgets/routing/fallbacks, approval checkpoints, workflow-level retry/cancel, event routing, and artifact handling — with production execution wired through the Rust kernel over gRPC.

On top of the core engine, this feature selectively incorporates capabilities inspired by the Hermes Agent (Nous Research) that fit VLoop's local-first, non-technical, orchestration-engine positioning: tools and toolsets, an on-demand skills system, persistent cross-session memory, context files/references, checkpoints and rollback, scheduled tasks, subagent delegation, sandboxed code execution, event hooks, MCP integration, and provider routing/fallback/credential pools. Advanced or peripheral capabilities (batch processing, OpenAI-compatible API server, pluggable memory providers, personality/plugin system) are included as explicitly optional, lower-priority requirements.

The feature preserves VLoop's architectural boundaries: the Control Plane (CP) is the cognitive authority that decides WHAT happens; the Rust kernel (`vloopd`) is the infrastructure authority that decides HOW and WHERE; secrets are granted by capability and never handled raw by the CP; and the React frontend communicates with the CP over HTTP/WebSocket APIs only.

## Glossary

- **Control_Plane**: The Python cognitive authority that owns orchestration, inference policy, workflow state, windows, and user interaction. Decides WHAT happens.
- **Kernel**: The Rust infrastructure daemon (`vloopd`) that owns infrastructure, resources, services, filesystems, networking, secrets, databases, supervision, and sandboxes. Decides HOW and WHERE.
- **Kernel_Adapter**: The Control_Plane component (`adapters/rust_infra.py`) that dispatches execution, streams logs, and tears down resources through Kernel gRPC.
- **Workflow**: A persisted unit of work consisting of a user objective, an execution plan (DAG), agent/tool steps, infrastructure requests, event history, artifacts, retry/cancel state, and approval checkpoints.
- **Workflow_Engine**: The Control_Plane subsystem that creates, plans, executes, observes, retries, and cancels Workflows.
- **Planner**: The Control_Plane component that transforms a user objective into an execution plan represented as a DAG.
- **DAG**: A directed acyclic graph of Workflow steps with declared dependencies. Each node is a Step.
- **Step**: A single node in a DAG that invokes an agent, a tool, a subagent, a code-execution job, or an approval checkpoint.
- **DAG_Executor**: The Control_Plane component that executes DAG Steps respecting dependency order and concurrency limits.
- **Agent**: A configured cognitive unit (model + instructions + input/output schema + enabled toolsets/skills) that the engine invokes.
- **Inference_Gateway**: The Control_Plane component that centralizes provider selection, model profiles, budgets, rate limits, retries, fallbacks, and prompt/tool-call policy for all model calls.
- **Provider_Router**: The Inference_Gateway component that selects a provider/model based on a routing strategy (cost, speed, quality) and performs failover.
- **Credential_Pool**: A set of secret-backed credentials for a single provider that the Inference_Gateway rotates across when rate limits or auth errors occur.
- **Budget**: A configured limit on token spend, monetary cost, or request count for a Workflow or scope.
- **Approval_Service**: The Control_Plane component that pauses a Workflow at an approval checkpoint and resumes it on user decision.
- **Approval_Checkpoint**: A Step that requires explicit user approval before dependent Steps execute.
- **Event_Router**: The Control_Plane component that translates Kernel event streams and internal engine events into user-facing Workflow state and frontend updates.
- **Artifact_Store**: The Control_Plane-facing record of outputs (files, results, pointers) produced by a Workflow and retained by the Kernel.
- **Toolset**: A named, enable/disable-able group of Tools.
- **Tool**: A callable function that extends an Agent (for example web search, sandboxed terminal, file editing, memory, delegation).
- **Toolset_Manager**: The Control_Plane component that registers Tools, groups them into Toolsets, and enforces which Toolsets an Agent may use.
- **Skill**: An on-demand knowledge document loaded into Agent context only when needed (progressive disclosure), compatible with the agentskills.io open standard.
- **Skills_Service**: The Control_Plane component that discovers, indexes, and loads Skills on demand.
- **Memory_Service**: The Control_Plane component that maintains bounded, curated cross-session memory of user preferences, projects, environment, and learned facts.
- **Context_Service**: The Control_Plane component that auto-discovers project context files and resolves @-references (files, folders, diffs, URLs) into Agent messages.
- **Checkpoint_Service**: The Control_Plane component that snapshots a Workflow working directory (via the Kernel) before file changes and restores it on rollback.
- **Scheduler**: The Control_Plane component that runs Workflows on a schedule defined by natural language or a cron expression.
- **Subagent_Manager**: The Control_Plane component that spawns child Agent instances with isolated context, restricted Toolsets, and concurrency limits.
- **Code_Execution_Service**: The Control_Plane component that runs Agent-generated scripts inside a Kernel-managed sandbox.
- **Hook_Service**: The Control_Plane component that runs registered custom code at Workflow/Step lifecycle points.
- **MCP_Service**: The Control_Plane component that connects to Model Context Protocol servers (stdio/HTTP) and exposes their filtered tools as Tools.
- **Workflow_Builder**: The frontend view through which a non-technical user composes, runs, observes, and controls Workflows without terminal use.
- **Sandbox**: A Kernel-managed, isolated execution environment (a workload of class `harness`, `worker`, `preview`, or `service`).

## Requirements

### Requirement 1: Workflow Lifecycle Management

**User Story:** As a non-technical professional, I want to create and manage automation workflows, so that I can run multi-step AI work without writing code.

#### Acceptance Criteria

1. WHEN a user submits a Workflow with a user objective, THE Workflow_Engine SHALL create a persisted Workflow record with a unique identifier and an initial status of `Created`.
2. WHEN a Workflow is created, THE Workflow_Engine SHALL persist the user objective, execution plan, steps, infrastructure requests, event history, artifacts, and retry/cancel state.
3. WHEN a user requests the list of Workflows, THE Control_Plane SHALL return all persisted Workflows with their current status.
4. WHEN a user requests a single Workflow by identifier, THE Control_Plane SHALL return the Workflow objective, current status, plan, step states, and event history.
5. IF a user submits a Workflow without a user objective, THEN THE Workflow_Engine SHALL reject the request and return a validation error identifying the missing objective.
6. WHEN a user deletes a Workflow that is not in an active execution state, THE Workflow_Engine SHALL remove the Workflow record and return a confirmation.

### Requirement 2: Workflow Planning and DAG Construction

**User Story:** As a non-technical professional, I want the system to turn my objective into a clear step-by-step plan, so that I can understand and trust what it will do before it runs.

#### Acceptance Criteria

1. WHEN a Workflow is created, THE Planner SHALL transform the user objective into an execution plan represented as a DAG of Steps.
2. THE Planner SHALL record, for each Step, the Step type, the assigned Agent or Tool, and the identifiers of the Steps it depends on.
3. IF the Planner produces a plan containing a dependency cycle, THEN THE Planner SHALL reject the plan and return an error identifying the cyclic Steps.
4. WHEN a plan is constructed, THE Control_Plane SHALL expose the plan to the frontend as an ordered, viewable list of Steps with their dependencies.
5. WHERE a user edits a proposed plan before execution, THE Workflow_Engine SHALL persist the edited plan as the execution plan for the Workflow.
6. IF a Step in a plan references an Agent or Tool that is not registered, THEN THE Planner SHALL reject the plan and return an error identifying the unresolved reference.

### Requirement 3: Multi-Agent DAG Execution

**User Story:** As a non-technical professional, I want multiple agents and steps to run in the right order, so that complex tasks complete reliably.

#### Acceptance Criteria

1. WHEN a user starts a Workflow, THE DAG_Executor SHALL execute Steps in an order that satisfies all declared dependencies.
2. WHILE a Step has unsatisfied dependencies, THE DAG_Executor SHALL hold that Step in a `Pending` state.
3. WHEN all dependencies of a Step complete successfully, THE DAG_Executor SHALL transition that Step to `Running` subject to the configured concurrency limit.
4. WHERE multiple Steps have satisfied dependencies and the concurrency limit permits, THE DAG_Executor SHALL execute those Steps concurrently.
5. WHEN a Step completes, THE DAG_Executor SHALL make that Step's output available as input to dependent Steps.
6. WHEN every Step in a Workflow reaches a terminal state, THE Workflow_Engine SHALL set the Workflow status to `Completed` if all Steps succeeded, or `Failed` if any non-recoverable Step failed.
7. IF a Step fails and no retry or fallback applies, THEN THE DAG_Executor SHALL stop scheduling Steps that depend on the failed Step and record the failure reason.

### Requirement 4: Workflow Retry and Cancellation

**User Story:** As a non-technical professional, I want to cancel a running workflow or retry a failed one, so that I stay in control when something goes wrong.

#### Acceptance Criteria

1. WHEN a user cancels a Workflow that is in an active execution state, THE Workflow_Engine SHALL transition the Workflow to `Cancelling` and request teardown of in-flight Steps through the Kernel_Adapter.
2. WHEN all in-flight Steps of a cancelled Workflow have stopped, THE Workflow_Engine SHALL set the Workflow status to `Cancelled` and preserve completed Step outputs and event history.
3. WHEN a user retries a `Failed` Workflow, THE Workflow_Engine SHALL re-execute the failed Steps and their unexecuted dependents while reusing the outputs of successfully completed Steps.
4. WHERE a Step is configured with a retry count, IF the Step fails, THEN THE DAG_Executor SHALL re-execute the Step up to the configured retry count before marking it failed.
5. IF a user requests retry of a Workflow that is not in a `Failed` or `Cancelled` state, THEN THE Workflow_Engine SHALL reject the request and return an error stating the current status.

### Requirement 5: Approval Checkpoints

**User Story:** As a non-technical professional, I want to approve sensitive steps before they run, so that the system never takes high-impact actions without my consent.

#### Acceptance Criteria

1. WHEN execution reaches an Approval_Checkpoint Step, THE Approval_Service SHALL pause the dependent Steps and set the Workflow status to `AwaitingApproval`.
2. WHEN a Workflow is `AwaitingApproval`, THE Control_Plane SHALL expose the pending approval, its context, and the proposed action to the frontend.
3. WHEN a user approves a pending Approval_Checkpoint, THE Approval_Service SHALL resume execution of the dependent Steps.
4. WHEN a user rejects a pending Approval_Checkpoint, THE Approval_Service SHALL cancel the dependent Steps and record the rejection reason.
5. WHILE a Workflow is `AwaitingApproval`, THE DAG_Executor SHALL NOT execute Steps that depend on the unresolved Approval_Checkpoint.

### Requirement 6: Inference Gateway with Budgets and Policy

**User Story:** As a non-technical professional, I want spending limits and consistent model behavior, so that automation does not run up unexpected costs.

#### Acceptance Criteria

1. WHEN an Agent or Step requires a model call, THE Inference_Gateway SHALL route the call rather than allowing direct provider access from orchestration code.
2. WHERE a Budget is configured for a Workflow, THE Inference_Gateway SHALL record the token and cost consumption of each model call against that Budget.
3. IF a model call would cause a Workflow to exceed its configured Budget, THEN THE Inference_Gateway SHALL block the call and set the Workflow status to `BudgetExceeded`.
4. WHERE a model profile is configured for an Agent, THE Inference_Gateway SHALL apply the profile's model, temperature, and token limits to the call unless overridden by the Step.
5. WHEN a provider returns a rate-limit response, THE Inference_Gateway SHALL retry the call according to the configured retry and backoff policy.
6. WHEN a model call completes, THE Inference_Gateway SHALL record the provider, model, token counts, and cost in the Workflow usage record.

### Requirement 7: Provider Routing, Fallback, and Credential Pools

**User Story:** As a non-technical professional, I want the system to keep working when one provider fails, so that my automation is resilient.

#### Acceptance Criteria

1. WHERE a routing strategy of cost, speed, or quality is configured, THE Provider_Router SHALL select the provider and model that best matches the configured strategy among the eligible providers.
2. IF a selected provider returns a non-recoverable error, THEN THE Provider_Router SHALL fail over to the next eligible provider in the configured fallback order.
3. WHERE a Credential_Pool with multiple credentials is configured for a provider, IF a credential returns a rate-limit or authentication error, THEN THE Inference_Gateway SHALL rotate to the next credential in the Credential_Pool.
4. IF all eligible providers and credentials for a model call are exhausted, THEN THE Inference_Gateway SHALL fail the call and record the exhaustion reason.
5. WHEN the Inference_Gateway requires a provider credential, THE Control_Plane SHALL request a secret grant from the Kernel by capability and SHALL NOT store or log the raw secret value.

### Requirement 8: Event Routing and Workflow Observability

**User Story:** As a non-technical professional, I want to watch my workflow as it runs, so that I can see progress and understand outcomes in real time.

#### Acceptance Criteria

1. WHEN a Step changes state, THE Event_Router SHALL emit a Workflow event recording the Step identifier, the new state, and a timestamp.
2. WHEN the Kernel emits a workload status, log, or lifecycle event for a Workflow's Step, THE Event_Router SHALL translate that event into a user-facing Workflow event.
3. THE Control_Plane SHALL stream Workflow events to the frontend over WebSocket as they occur.
4. WHEN a user requests a Workflow's event history, THE Control_Plane SHALL return the ordered list of recorded events for that Workflow.
5. IF the connection between the Control_Plane and the Kernel is interrupted during execution, THEN THE Event_Router SHALL record a connectivity event and reconcile Step states when the connection is restored.

### Requirement 8a: Artifact Handling

**User Story:** As a non-technical professional, I want to access the files and results a workflow produced, so that I can use the output of my automation.

#### Acceptance Criteria

1. WHEN a Step produces an output file or result retained by the Kernel, THE Artifact_Store SHALL record an artifact entry referencing the Kernel-held artifact for the owning Workflow.
2. WHEN a user requests the artifacts of a Workflow, THE Control_Plane SHALL return the list of artifact entries with their names, types, and Kernel pointers.
3. WHEN a user requests retrieval of an artifact, THE Control_Plane SHALL obtain the artifact content through the Kernel and return it to the frontend.
4. WHEN a Workflow is deleted, THE Workflow_Engine SHALL request release of that Workflow's ephemeral artifacts through the Kernel while retaining artifacts the user marked for retention.

### Requirement 9: Production Execution via the Kernel

**User Story:** As a non-technical professional, I want generated code and tasks to run safely in a managed sandbox, so that automation cannot damage my computer.

#### Acceptance Criteria

1. WHEN a Step requires execution of code or a task, THE Kernel_Adapter SHALL dispatch the execution to the Kernel as a typed workload over gRPC.
2. THE Kernel_Adapter SHALL request the appropriate workload class (`harness`, `worker`, `preview`, or `service`) for each dispatched Step based on the Step's execution intent.
3. WHEN the Kernel reports a workload state transition, THE Kernel_Adapter SHALL map the transition to the corresponding Step state.
4. WHEN a Step's workload runs, THE Kernel_Adapter SHALL stream the workload's stdout and stderr logs to the Event_Router.
5. WHEN a Workflow Step is cancelled, THE Kernel_Adapter SHALL request workload teardown through the Kernel and confirm release of grants, routes, and ephemeral mounts.
6. THE Control_Plane SHALL NOT invoke Docker, Kubernetes, or arbitrary host execution directly in the production path.

### Requirement 10: Tools and Toolsets

**User Story:** As a non-technical professional, I want to turn capabilities on or off per agent, so that each agent can only do what I allow.

#### Acceptance Criteria

1. THE Toolset_Manager SHALL maintain a registry of available Tools grouped into named Toolsets.
2. WHERE a Toolset is enabled for an Agent, THE Toolset_Manager SHALL make that Toolset's Tools available to the Agent during invocation.
3. WHERE a Toolset is disabled for an Agent, IF the Agent attempts to call a Tool from that Toolset, THEN THE Toolset_Manager SHALL deny the call and record the denial.
4. WHEN a user views an Agent's configuration, THE Control_Plane SHALL return the list of available Toolsets and which Toolsets are enabled for the Agent.
5. WHEN a Tool that performs execution or file access is invoked, THE Toolset_Manager SHALL route the Tool's effects through the Kernel rather than executing them directly in the Control_Plane.

### Requirement 11: Skills System (On-Demand Knowledge)

**User Story:** As a non-technical professional, I want agents to load relevant know-how only when needed, so that they perform well without me managing prompts.

#### Acceptance Criteria

1. THE Skills_Service SHALL discover and index Skill documents that conform to the agentskills.io open standard.
2. WHEN an Agent invocation matches a Skill's applicability criteria, THE Skills_Service SHALL load that Skill's content into the Agent's context for the invocation.
3. WHERE a Skill is not applicable to an invocation, THE Skills_Service SHALL exclude that Skill's content from the Agent's context.
4. WHEN a user attaches a Skill to a Workflow or Step, THE Skills_Service SHALL load that Skill for the relevant invocations.
5. WHEN a user requests the list of available Skills, THE Control_Plane SHALL return each Skill's name, description, and applicability summary.

### Requirement 12: Persistent Cross-Session Memory

**User Story:** As a non-technical professional, I want the system to remember my preferences and projects, so that I do not repeat myself across sessions.

#### Acceptance Criteria

1. WHEN a user records a preference, project fact, or environment fact, THE Memory_Service SHALL persist that entry in curated cross-session memory.
2. WHEN an Agent invocation begins, THE Memory_Service SHALL load the relevant curated memory entries into the Agent's context.
3. WHERE the curated memory exceeds its configured size bound, THE Memory_Service SHALL retain the highest-priority entries within the bound and record which entries were evicted.
4. WHEN a user views stored memory, THE Control_Plane SHALL return the curated memory entries.
5. WHEN a user deletes a memory entry, THE Memory_Service SHALL remove that entry from curated memory.

### Requirement 13: Context Files and References

**User Story:** As a non-technical professional, I want to point an agent at my files or a URL, so that it works with my actual material.

#### Acceptance Criteria

1. WHERE a project context file is present in a Workflow's working directory, THE Context_Service SHALL auto-discover and load that file into the relevant Agent context.
2. WHEN a user includes an @-reference to a file, folder, diff, or URL in a message, THE Context_Service SHALL resolve the reference and inject the referenced content into the Agent message.
3. IF an @-reference cannot be resolved, THEN THE Context_Service SHALL record an unresolved-reference notice and continue the invocation with the resolvable content.
4. WHEN the Context_Service reads files or fetches URLs, THE Context_Service SHALL obtain that content through the Kernel filesystem and network capabilities rather than direct host access.

### Requirement 14: Checkpoints and Rollback

**User Story:** As a non-technical professional, I want to undo file changes a workflow made, so that I can recover if the result is wrong.

#### Acceptance Criteria

1. WHEN a Step is about to modify files in a Workflow working directory, THE Checkpoint_Service SHALL request a snapshot of the working directory through the Kernel before the modification.
2. WHEN a user requests rollback to a checkpoint, THE Checkpoint_Service SHALL restore the working directory to the snapshot through the Kernel.
3. WHEN a user requests the checkpoints of a Workflow, THE Control_Plane SHALL return the list of checkpoints with their timestamps and associated Steps.
4. IF a checkpoint snapshot cannot be created before a file-modifying Step, THEN THE Checkpoint_Service SHALL record the failure and the Workflow_Engine SHALL pause the Step pending user confirmation.

### Requirement 15: Scheduled Tasks

**User Story:** As a non-technical professional, I want to schedule recurring automations, so that work happens on time without me starting it.

#### Acceptance Criteria

1. WHEN a user creates a scheduled task with a cron expression or a natural-language schedule, THE Scheduler SHALL persist the schedule and the associated Workflow definition.
2. WHEN a scheduled task's trigger time is reached, THE Scheduler SHALL start a new Workflow run from the associated definition.
3. WHEN a user pauses a scheduled task, THE Scheduler SHALL stop triggering new runs until the task is resumed.
4. WHEN a user edits a scheduled task's schedule, THE Scheduler SHALL apply the new schedule to subsequent trigger evaluations.
5. WHEN a scheduled run completes, THE Scheduler SHALL record the run outcome against the scheduled task's history.
6. WHERE a Skill is attached to a scheduled task, THE Scheduler SHALL load that Skill for the scheduled run.

### Requirement 16: Subagent Delegation

**User Story:** As a non-technical professional, I want an agent to delegate parts of a job to helper agents, so that large tasks finish faster.

#### Acceptance Criteria

1. WHEN an Agent delegates a subtask, THE Subagent_Manager SHALL spawn a child Agent instance with a context isolated from the parent Agent.
2. THE Subagent_Manager SHALL restrict a child Agent to the Toolsets configured for delegation.
3. WHERE a concurrency limit for subagents is configured, THE Subagent_Manager SHALL run at most that number of child Agents at the same time.
4. WHEN a child Agent completes, THE Subagent_Manager SHALL return the child Agent's result to the parent Agent.
5. WHEN a parent Workflow is cancelled, THE Subagent_Manager SHALL cancel all child Agents spawned by that Workflow.

### Requirement 17: Sandboxed Code Execution

**User Story:** As a non-technical professional, I want agents to write and run scripts safely, so that they can complete multi-step work in one go.

#### Acceptance Criteria

1. WHEN an Agent produces a script to execute, THE Code_Execution_Service SHALL dispatch the script to a Kernel-managed Sandbox through the Kernel_Adapter.
2. WHILE a script runs in a Sandbox, THE Code_Execution_Service SHALL stream the script's output to the Event_Router.
3. WHEN a script completes, THE Code_Execution_Service SHALL return the script's exit code, output, and produced artifacts to the invoking Step.
4. THE Code_Execution_Service SHALL NOT execute Agent-generated scripts on the host outside a Kernel-managed Sandbox.
5. IF a script exceeds its configured execution time limit, THEN THE Code_Execution_Service SHALL request Sandbox termination through the Kernel and record a timeout result.

### Requirement 18: Event Hooks

**User Story:** As a power user supporting non-technical colleagues, I want to attach custom actions to lifecycle events, so that I can add logging, alerts, and guardrails.

#### Acceptance Criteria

1. THE Hook_Service SHALL allow registration of hooks bound to defined Workflow and Step lifecycle points.
2. WHEN a lifecycle point with a registered hook is reached, THE Hook_Service SHALL execute the bound hook and provide the lifecycle event context.
3. WHERE a hook is configured as blocking, THE Hook_Service SHALL await the hook's result before continuing the lifecycle transition.
4. IF a blocking hook returns a denial, THEN THE Hook_Service SHALL stop the associated lifecycle transition and record the denial reason.
5. IF a non-blocking hook fails, THEN THE Hook_Service SHALL record the failure and continue the lifecycle transition.

### Requirement 19: MCP Integration

**User Story:** As a non-technical professional, I want to connect external tool servers, so that my agents can use additional capabilities I rely on.

#### Acceptance Criteria

1. WHEN a user configures an MCP server with a stdio or HTTP transport, THE MCP_Service SHALL connect to the server and retrieve its advertised tools.
2. WHERE a per-server tool filter is configured, THE MCP_Service SHALL expose only the filtered tools as Tools in the Toolset_Manager.
3. WHEN an Agent calls an MCP-provided Tool, THE MCP_Service SHALL forward the call to the MCP server and return the result to the Agent.
4. IF an MCP server connection fails, THEN THE MCP_Service SHALL mark that server's Tools unavailable and record the connection failure.
5. WHERE an MCP server requires a credential, THE Control_Plane SHALL obtain the credential through a Kernel secret grant by capability.

### Requirement 20: Non-Technical Visual Workflow Experience

**User Story:** As a non-technical professional, I want to build and run workflows visually, so that I never need a terminal or code.

#### Acceptance Criteria

1. THE Workflow_Builder SHALL allow a user to create, configure, run, observe, cancel, and retry a Workflow entirely through the frontend.
2. THE Workflow_Builder SHALL present the execution plan as a visual sequence of Steps with their current states.
3. WHEN a Workflow requires a decision at an Approval_Checkpoint, THE Workflow_Builder SHALL present an approve/reject control with the proposed action described in plain language.
4. WHEN a configuration value the user provides is invalid, THE Control_Plane SHALL return a validation error that names the field and the expected value.
5. THE Control_Plane SHALL serve all Workflow_Builder data and actions over HTTP/WebSocket APIs only.

### Requirement 21: Safe-By-Default Configuration

**User Story:** As a non-technical professional, I want the system to be safe by default, so that I do not accidentally grant dangerous capabilities.

#### Acceptance Criteria

1. WHEN a new Agent is created, THE Toolset_Manager SHALL enable only Toolsets that perform no host file modification, no network access, and no code execution by default.
2. WHERE an Agent is granted a Toolset that performs file modification, network access, or code execution, THE Control_Plane SHALL require explicit user confirmation before enabling that Toolset.
3. WHEN a Workflow requests network access, file modification, or code execution at runtime, THE Control_Plane SHALL request the corresponding capability from the Kernel rather than acting directly.
4. THE Control_Plane SHALL record an audit event for each capability grant request and each high-impact action a Workflow performs.

### Requirement 22 (Optional): Batch Processing

**User Story:** As a power user, I want to run an agent across many inputs at once, so that I can evaluate and process work at scale.

#### Acceptance Criteria

1. WHERE batch processing is enabled, WHEN a user submits a batch of inputs for an Agent, THE Workflow_Engine SHALL run the Agent across the inputs subject to the configured concurrency limit.
2. WHERE batch processing is enabled, WHEN a batch completes, THE Workflow_Engine SHALL return a structured result for each input including its output and trajectory.
3. WHERE batch processing is enabled, IF an individual input fails, THEN THE Workflow_Engine SHALL record that input's failure and continue processing the remaining inputs.

### Requirement 23 (Optional): OpenAI-Compatible API Server

**User Story:** As a power user, I want to connect external frontends to the engine, so that I can reuse existing tools.

#### Acceptance Criteria

1. WHERE the OpenAI-compatible API server is enabled, THE Control_Plane SHALL expose an HTTP endpoint that accepts OpenAI-compatible chat completion requests.
2. WHERE the OpenAI-compatible API server is enabled, WHEN a compatible request is received, THE Control_Plane SHALL route the request through the Inference_Gateway and return an OpenAI-compatible response.
3. WHERE the OpenAI-compatible API server is enabled, THE Control_Plane SHALL require an authentication credential for each request to the endpoint.

### Requirement 24 (Optional): Pluggable Memory Providers

**User Story:** As a power user, I want to use an external memory backend, so that memory can scale beyond the local default.

#### Acceptance Criteria

1. WHERE an external memory provider is configured, THE Memory_Service SHALL read and write curated memory through that provider instead of the local default.
2. WHERE an external memory provider is configured, IF the provider is unavailable, THEN THE Memory_Service SHALL record the failure and fall back to the local default memory store.

### Requirement 25 (Optional): Personality and Plugin System

**User Story:** As a power user, I want to customize agent identity and add tools without changing core code, so that I can tailor the engine to my needs.

#### Acceptance Criteria

1. WHERE a personality profile is configured for an Agent, THE Control_Plane SHALL apply the profile's identity instructions to the Agent's context.
2. WHERE a plugin that registers Tools or hooks is installed, THE Control_Plane SHALL register the plugin's Tools and hooks without modification to core modules.
3. IF a plugin fails to load, THEN THE Control_Plane SHALL record the load failure and continue operating with the remaining plugins.
