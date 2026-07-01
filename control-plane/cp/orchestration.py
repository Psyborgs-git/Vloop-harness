"""Orchestration subsystem construction and runtime accessor wiring.

This module is the central integration point for the orchestration engine: it
builds the Control_Plane orchestration subsystems (Planner, DAG_Executor,
Scheduler, Checkpoint_Manager, Approval_Manager, Memory_Store, Tool_Registry,
MCP_Client, Provider_Router, Event_Router, Workflow_Serializer) and implements
the ``runtime.<accessor>`` methods that the HTTP handlers in
:mod:`cp.handlers` call.

The accessor contracts are documented in each handler module's docstring
(``cp/handlers/workflows.py``, ``schedules.py``, ``memory.py``,
``checkpoints.py``, ``tools.py``, ``mcp.py``). Every accessor returns
JSON-serializable dicts/lists so the handlers can pass results straight to
``write_json``.

Design notes
------------
* ``core`` never imports ``cp`` — all subsystem construction lives here in
  ``cp``. The subsystems depend only on the shared ``DatabaseBackend`` and small
  duck-typed collaborators.
* Pure-Python subsystems (Planner, Tool_Registry) and DB-backed subsystems
  (Memory_Store, Scheduler, Checkpoint_Manager, Approval_Manager, DAG_Executor)
  are constructed eagerly. Subsystems that need a live Kernel gRPC stub (the
  execution manager that performs sandbox snapshots/teardown) are reached
  through :class:`_LazyExecutionManager`, a thin adapter that delegates to the
  runtime's real execution manager once kernel registration has wired it up and
  raises a descriptive error before then. This keeps construction (and the
  handler unit tests) free of any kernel dependency.
* :class:`OrchestrationMixin` is mixed into
  :class:`cp.runtime.ControlPlaneRuntime`. It expects ``self.db`` (a
  :class:`~core.database.DatabaseBackend`) and, optionally,
  ``self.agent_orchestrator`` to be set before :meth:`_init_orchestration` runs.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from core.approval_manager import ApprovalManager
from core.checkpoint_manager import CheckpointManager
from core.dag_executor import DagExecutor
from core.event_router import EventRouter
from core.helpers import from_json, now_iso, to_json
from core.memory_store import MemoryStore
from core.planner import Planner, ReferenceResolver, ValidationError
from core.provider_router import ProviderRouter
from core.scheduler import Scheduler
from core.tool_registry import ToolRegistry
from core.workflow_serializer import WorkflowSerializer

LOGGER = logging.getLogger("vloop.control_plane.orchestration")


# ---------------------------------------------------------------------------
# Lazy kernel execution manager adapter
# ---------------------------------------------------------------------------


class _LazyExecutionManager:
    """Defers to the runtime's kernel-backed execution manager once available.

    The real execution manager (``adapters.rust_infra.RustInfraExecutionManager``)
    can only be built once the Control_Plane has a live Kernel gRPC stub, which
    happens after kernel registration. Subsystems that need it
    (Checkpoint_Manager for snapshots, DAG_Executor for workload teardown) are
    constructed eagerly with this adapter instead, so they can be wired at
    ``__init__`` time. Each call delegates to ``runtime._execution_manager`` if
    set, otherwise raises a descriptive error rather than crashing — there is no
    host fallback (Req 21.2).
    """

    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime

    def _delegate(self) -> Any:
        manager = getattr(self._runtime, "_execution_manager", None)
        if manager is None:
            raise RuntimeError(
                "kernel execution manager is not available yet; the Control_Plane "
                "must register with the Kernel before sandbox-backed operations "
                "can run (no host fallback)"
            )
        return manager

    def snapshot_workspace(self, workspace_id: str) -> str:
        return self._delegate().snapshot_workspace(workspace_id)

    def restore_workspace(self, workspace_id: str, snap: str) -> None:
        self._delegate().restore_workspace(workspace_id, snap)

    def teardown(self, job_id: str) -> None:
        self._delegate().teardown(job_id)

    def dispatch_job(self, spec: dict[str, Any], policy: dict[str, Any]) -> str:
        return self._delegate().dispatch_job(spec, policy)

    def request_secret_grant(self, secret_ref: str, target: str) -> Any:
        return self._delegate().request_secret_grant(secret_ref, target)

    def stream_logs(self, job_id: str) -> Any:
        return self._delegate().stream_logs(job_id)


class _ToolLookupAdapter:
    """Adapts the Tool_Registry to the Planner's ``ToolLookup`` protocol.

    The Planner resolves a step's tool reference via ``has_tool(name)``; the
    Tool_Registry exposes ``get_tool`` instead, so this thin adapter bridges the
    two without coupling the Planner to the registry's wider surface.
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def has_tool(self, tool_name: str) -> bool:
        return self._registry.get_tool(tool_name) is not None


# ---------------------------------------------------------------------------
# Startup helper (Requirements 3.7, 8.5)
# ---------------------------------------------------------------------------


def resume_pending_runs_at_startup(
    executor: Any, *, logger: logging.Logger = LOGGER
) -> list[str]:
    """Resume non-terminal Workflow_Runs at boot, never crashing startup.

    Calls :meth:`~core.dag_executor.DagExecutor.resume_pending_runs` so that
    runs left ``pending``/``running``/``awaiting_approval`` survive a
    Control_Plane restart (Requirements 3.7, 8.5). Any failure is logged and
    swallowed so a resume problem can never prevent the Control_Plane from
    booting (Requirement 20.1); the empty list is returned in that case.
    """
    if executor is None:
        return []
    try:
        resumed = executor.resume_pending_runs(block=False)
    except Exception as exc:  # noqa: BLE001 - resume must never crash boot
        logger.exception("failed to resume pending workflow runs at startup: %s", exc)
        return []
    if resumed:
        logger.info(
            "resumed %d pending workflow run(s) at startup: %s",
            len(resumed),
            ", ".join(resumed),
        )
    return list(resumed or [])


# ---------------------------------------------------------------------------
# Orchestration mixin
# ---------------------------------------------------------------------------


class OrchestrationMixin:
    """Constructs orchestration subsystems and implements runtime accessors.

    Mixed into :class:`cp.runtime.ControlPlaneRuntime`. Call
    :meth:`_init_orchestration` from ``__init__`` once ``self.db`` (and,
    optionally, ``self.agent_orchestrator``) exist.
    """

    # These attributes are provided by the host runtime.
    db: Any
    agent_orchestrator: Any

    # -- construction -------------------------------------------------------

    def _init_orchestration(self) -> None:
        """Build every orchestration subsystem and wire their dependencies."""
        # The kernel-backed execution manager is wired in after registration;
        # subsystems reach it lazily until then.
        self._execution_manager: Any = None

        # Workflow event stream (per-run, persisted, secret-redacted history).
        self.workflow_events = EventRouter(self.db)
        self.workflow_serializer = WorkflowSerializer()

        # Pure-Python catalogs.
        self.tool_registry = ToolRegistry(event_router=self.workflow_events)
        self.provider_router = ProviderRouter()

        # DB-backed subsystems.
        self.memory_store = MemoryStore(self.db)
        self.planner = Planner(
            ReferenceResolver(
                agents=getattr(self, "agent_orchestrator", None),
                tools=_ToolLookupAdapter(self.tool_registry),
            )
        )
        self.approval_manager = ApprovalManager(self.db, self.workflow_events)
        self.dag_executor = DagExecutor(
            self.db,
            agents=getattr(self, "agent_orchestrator", None),
            tools=self.tool_registry,
            approvals=self.approval_manager,
            events=self.workflow_events,
            infra=_LazyExecutionManager(self),
            serializer=self.workflow_serializer,
        )
        # The executor and approval manager hold a mutual reference so an
        # approval decision can resume the run (see ApprovalManager.approve).
        self.approval_manager.attach_executor(self.dag_executor)
        self.scheduler = Scheduler(self.db, self.dag_executor)
        self.checkpoint_manager = CheckpointManager(
            self.db, _LazyExecutionManager(self)
        )

        # MCP_Client needs a concrete transport (network/process), which is not
        # a pure-Python construct; it is wired when a transport is configured.
        self.mcp_client: Any = None

        # In-memory per-scope toolset enablement and the workflow template
        # catalog. The template catalog is populated by a later task (30.11);
        # an empty catalog keeps the routes functional in the meantime.
        self._toolset_scope_enabled: dict[str, dict[str, bool]] = {}
        self._workflow_templates: dict[str, dict[str, Any]] = {}

    # ======================================================================
    # Workflows (cp/handlers/workflows.py)
    # ======================================================================

    def list_workflows(self) -> list[dict[str, Any]]:
        rows = self.db.fetch_all(
            "SELECT id, name, objective, definition_json, revision, created_at, "
            "updated_at FROM workflow_definitions ORDER BY created_at ASC, id ASC"
        )
        return [self._workflow_view(row) for row in rows]

    def get_workflow(self, workflow_id: str) -> dict[str, Any] | None:
        row = self.db.fetch_one(
            "SELECT id, name, objective, definition_json, revision, created_at, "
            "updated_at FROM workflow_definitions WHERE id = ?",
            (workflow_id,),
        )
        return self._workflow_view(row) if row is not None else None

    def validate_workflow(self, body: dict[str, Any]) -> dict[str, Any]:
        """Validate a definition without persisting or assigning an id.

        Pure and side-effect free (Requirements 1.4, 1.5): returns the Planner's
        problem list, never a new id.
        """
        problems = self.planner.validate(body or {})
        return {"valid": not problems, "problems": problems}

    def create_workflow(self, body: dict[str, Any]) -> dict[str, Any]:
        """Validate via the Planner and persist only on success (Req 1.4).

        An invalid definition raises ``ValueError`` (mapped to 400 by the HTTP
        shell) and is never persisted or assigned an id.
        """
        definition = body or {}
        self._compile_or_raise(definition)
        return self._persist_workflow(definition)

    def list_workflow_templates(self) -> list[dict[str, Any]]:
        return list(self._workflow_templates.values())

    def get_workflow_template(self, template_id: str) -> dict[str, Any] | None:
        return self._workflow_templates.get(template_id)

    def instantiate_workflow_template(
        self, template_id: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        """Instantiate a template into a validated, persisted Workflow (Req 20.2)."""
        template = self.get_workflow_template(template_id)
        if template is None:
            raise KeyError(f"workflow template `{template_id}` was not found")
        definition = dict(template.get("definition") or {})
        # Allow the caller to override top-level fields (name, inputs, ...).
        for key, value in (body or {}).items():
            definition[key] = value
        self._compile_or_raise(definition)
        return self._persist_workflow(definition)

    def start_workflow_run(
        self, workflow_id: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        """Start a Workflow_Run for a definition and begin execution (Req 3.1, 20.1)."""
        concurrency = None
        if body:
            concurrency = body.get("concurrencyLimit") or body.get(
                "concurrency_limit"
            )
        run_id = self.dag_executor.start_run(
            workflow_id, concurrency_limit=concurrency
        )
        try:
            # Drive the run on the executor's own worker threads; never block
            # the calling HTTP request.
            self.dag_executor.execute_run(run_id, block=False)
        except Exception as exc:  # noqa: BLE001 - run start is best-effort
            LOGGER.exception(
                "workflow run '%s' failed to begin executing: %s", run_id, exc
            )
        return self.dag_executor.get_run(run_id)["run"]

    def list_workflow_runs(self, workflow_id: str) -> list[dict[str, Any]]:
        rows = self.db.fetch_all(
            "SELECT * FROM workflow_runs WHERE definition_id = ? "
            "ORDER BY created_at DESC, id ASC",
            (workflow_id,),
        )
        return [dict(row) for row in rows]

    def get_workflow_run(self, run_id: str) -> dict[str, Any]:
        """Observe a run: state, step states, and event history (Req 4.5)."""
        return self.dag_executor.get_run(run_id)

    def cancel_workflow_run(self, run_id: str) -> dict[str, Any]:
        """Cancel a run, tearing down in-flight workloads (Req 4.2)."""
        self.dag_executor.cancel_run(run_id)
        return self.dag_executor.get_run(run_id)["run"]

    def retry_workflow_run(self, run_id: str) -> dict[str, Any]:
        """Retry the error closure of a failed run (Req 4.4)."""
        self.dag_executor.retry_run(run_id, block=False)
        return self.dag_executor.get_run(run_id)["run"]

    # -- workflow helpers ---------------------------------------------------

    def _compile_or_raise(self, definition: dict[str, Any]) -> None:
        """Compile a definition via the Planner, raising ValueError on rejection.

        The Planner raises :class:`~core.planner.ValidationError` (not a
        ``ValueError``); the HTTP shell maps validation failures to 400 via
        ``ValueError``, so the primary problem is re-raised as one. No
        persistence or id assignment happens here (Req 1.4).
        """
        try:
            self.planner.build_dag(definition)
        except ValidationError as exc:
            raise ValueError(exc.message) from exc

    def _persist_workflow(self, definition: dict[str, Any]) -> dict[str, Any]:
        """Persist a validated definition canonically and return its view."""
        serialized = self.workflow_serializer.serialize(definition)
        canonical = self.workflow_serializer.deserialize(serialized)
        workflow_id = str(uuid.uuid4())
        ts = now_iso()
        self.db.execute(
            "INSERT INTO workflow_definitions "
            "(id, name, objective, definition_json, revision, created_at, "
            "updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                workflow_id,
                canonical.get("name") or "untitled",
                canonical.get("objective") or "",
                serialized,
                1,
                ts,
                ts,
            ),
        )
        return self.get_workflow(workflow_id)  # type: ignore[return-value]

    def _workflow_view(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "objective": row["objective"],
            "definition": self.workflow_serializer.deserialize(
                row["definition_json"]
            ),
            "revision": row["revision"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    # ======================================================================
    # Schedules (cp/handlers/schedules.py)
    # ======================================================================

    def list_scheduled_tasks(
        self, *, definition_id: str | None = None
    ) -> list[dict[str, Any]]:
        return self.scheduler.list_tasks(definition_id=definition_id)

    def create_scheduled_task(
        self, definition_id: str, cron_expression: str, *, state: str = "active"
    ) -> dict[str, Any]:
        return self.scheduler.create(definition_id, cron_expression, state=state)

    def pause_scheduled_task(self, task_id: str) -> dict[str, Any]:
        return self.scheduler.pause(task_id)

    def resume_scheduled_task(self, task_id: str) -> dict[str, Any]:
        return self.scheduler.resume(task_id)

    # ======================================================================
    # Memory (cp/handlers/memory.py)
    # ======================================================================

    def list_memory_entries(
        self, category: str | None = None
    ) -> list[dict[str, Any]]:
        return self.memory_store.list_entries(category)

    def record_memory_entry(
        self, content: str, category: str | None = None
    ) -> dict[str, Any]:
        if category is None:
            return self.memory_store.record(content)
        return self.memory_store.record(content, category)

    def delete_memory_entry(self, entry_id: str) -> None:
        self.memory_store.delete(entry_id)

    # ======================================================================
    # Checkpoints (cp/handlers/checkpoints.py)
    # ======================================================================

    def list_checkpoints(self, run_id: str) -> list[dict[str, Any]]:
        return self.checkpoint_manager.list_checkpoints(run_id)

    def restore_checkpoint(self, checkpoint_id: str) -> dict[str, Any]:
        return self.checkpoint_manager.restore(checkpoint_id)

    # ======================================================================
    # Approvals (cp/handlers/approvals.py)
    # ======================================================================

    def pending_approvals(self, run_id: str) -> list[dict[str, Any]]:
        """List the checkpoints in a run awaiting a decision (Req 8.2, 8.5)."""
        return self.approval_manager.pending_for_run(run_id)

    def approve_checkpoint(
        self, run_id: str, step_id: str, edits: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Approve a checkpoint and resume the run from it (Req 8.3).

        The run is resumed on the executor's own worker threads
        (``block=False``) so the HTTP request never blocks on execution; the
        refreshed run view is returned immediately.
        """
        self.approval_manager.approve(run_id, step_id, edits, block=False)
        return self.dag_executor.get_run(run_id)["run"]

    def reject_checkpoint(
        self, run_id: str, step_id: str, reason: str
    ) -> dict[str, Any]:
        """Reject a checkpoint, terminating the run as ``rejected`` (Req 8.4)."""
        self.approval_manager.reject(run_id, step_id, reason)
        return self.dag_executor.get_run(run_id)["run"]

    # ======================================================================
    # Tools / Toolsets (cp/handlers/tools.py)
    # ======================================================================

    def list_tools(self, *, scope: str | None = None) -> list[dict[str, Any]]:
        return [
            self._tool_view(tool, scope) for tool in self.tool_registry.list_tools()
        ]

    def list_toolsets(self, *, scope: str | None = None) -> list[dict[str, Any]]:
        return [
            self._toolset_view(ts, scope)
            for ts in self.tool_registry.list_toolsets()
        ]

    def set_tool_enabled(
        self, tool_name: str, scope: str, enabled: bool
    ) -> dict[str, Any]:
        tool = self.tool_registry.get_tool(tool_name)
        if tool is None:
            raise KeyError(f"tool `{tool_name}` was not found")
        self._set_scope_toolset(tool.toolset, scope, enabled)
        return self._tool_view(tool, scope)

    def set_toolset_enabled(
        self, toolset_id: str, scope: str, enabled: bool
    ) -> dict[str, Any]:
        toolset = next(
            (ts for ts in self.tool_registry.list_toolsets() if ts.id == toolset_id),
            None,
        )
        if toolset is None:
            raise KeyError(f"toolset `{toolset_id}` was not found")
        self._set_scope_toolset(toolset_id, scope, enabled)
        return self._toolset_view(toolset, scope)

    # -- tool helpers -------------------------------------------------------

    def _set_scope_toolset(self, toolset: str, scope: str, enabled: bool) -> None:
        self._toolset_scope_enabled.setdefault(scope, {})[toolset] = bool(enabled)

    def _scope_toolset_enabled(self, toolset: str, scope: str) -> bool:
        return self._toolset_scope_enabled.get(scope, {}).get(toolset, False)

    def _tool_view(self, tool: Any, scope: str | None) -> dict[str, Any]:
        view: dict[str, Any] = {
            "name": tool.name,
            "description": tool.description,
            "toolset": tool.toolset,
            "mutating": tool.mutating,
            "available": self.tool_registry.is_available(tool.name),
        }
        if scope is not None:
            view["scope"] = scope
            view["enabled"] = view["available"] and self._scope_toolset_enabled(
                tool.toolset, scope
            )
        return view

    def _toolset_view(self, toolset: Any, scope: str | None) -> dict[str, Any]:
        view: dict[str, Any] = {
            "id": toolset.id,
            "name": toolset.name,
            "tools": list(toolset.tools),
        }
        if scope is not None:
            view["scope"] = scope
            view["enabled"] = self._scope_toolset_enabled(toolset.id, scope)
        return view

    # ======================================================================
    # MCP servers (cp/handlers/mcp.py)
    # ======================================================================

    def list_mcp_servers(self) -> list[dict[str, Any]]:
        rows = self.db.fetch_all(
            "SELECT id, name, transport, tool_filter_json, grant_ref, status, "
            "created_at FROM mcp_servers ORDER BY created_at ASC, id ASC"
        )
        return [self._mcp_view(row) for row in rows]

    def get_mcp_server(self, server_id: str) -> dict[str, Any] | None:
        row = self._mcp_row(server_id)
        return self._mcp_view(row) if row is not None else None

    def configure_mcp_server(self, config: dict[str, Any]) -> dict[str, Any]:
        config = config or {}
        name = config.get("name")
        transport = config.get("transport")
        if not name or not transport:
            raise ValueError(
                "an MCP server connection requires a 'name' and a 'transport'"
            )
        server_id = config.get("id") or str(uuid.uuid4())
        raw_filter = config.get("toolFilter")
        if raw_filter is None:
            raw_filter = config.get("tool_filter")
        tool_filter_json = (
            to_json(list(raw_filter)) if raw_filter is not None else None
        )
        grant_ref = (
            config.get("secretRef")
            or config.get("secret_ref")
            or config.get("grantRef")
            or config.get("grant_ref")
        )

        existing = self._mcp_row(server_id)
        if existing is None:
            status = config.get("status") or "disconnected"
            self.db.execute(
                "INSERT INTO mcp_servers "
                "(id, name, transport, tool_filter_json, grant_ref, status, "
                "created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    server_id,
                    name,
                    transport,
                    tool_filter_json,
                    grant_ref,
                    status,
                    now_iso(),
                ),
            )
        else:
            self.db.execute(
                "UPDATE mcp_servers SET name = ?, transport = ?, "
                "tool_filter_json = ?, grant_ref = ? WHERE id = ?",
                (name, transport, tool_filter_json, grant_ref, server_id),
            )
        return self.get_mcp_server(server_id)  # type: ignore[return-value]

    def remove_mcp_server(self, server_id: str) -> None:
        if self._mcp_row(server_id) is None:
            raise KeyError(f"MCP server `{server_id}` was not found")
        self.db.execute("DELETE FROM mcp_servers WHERE id = ?", (server_id,))

    def connect_mcp_server(self, server_id: str) -> dict[str, Any]:
        if self._mcp_row(server_id) is None:
            raise KeyError(f"MCP server `{server_id}` was not found")
        client = self._require_mcp_client()
        client.connect(self._mcp_config(server_id))
        return self.get_mcp_server(server_id)  # type: ignore[return-value]

    def disconnect_mcp_server(self, server_id: str) -> dict[str, Any]:
        if self._mcp_row(server_id) is None:
            raise KeyError(f"MCP server `{server_id}` was not found")
        client = self._require_mcp_client()
        client.disconnect(server_id)
        return self.get_mcp_server(server_id)  # type: ignore[return-value]

    # -- mcp helpers --------------------------------------------------------

    def _mcp_row(self, server_id: str) -> dict[str, Any] | None:
        return self.db.fetch_one(
            "SELECT id, name, transport, tool_filter_json, grant_ref, status, "
            "created_at FROM mcp_servers WHERE id = ?",
            (server_id,),
        )

    def _mcp_view(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "transport": row["transport"],
            "toolFilter": from_json(row.get("tool_filter_json"), None),
            "grantRef": row.get("grant_ref"),
            "status": row["status"],
            "createdAt": row["created_at"],
        }

    def _mcp_config(self, server_id: str) -> Any:
        """Build an :class:`~core.mcp_client.MCPServerConfig` from persistence."""
        from core.mcp_client import MCPServerConfig

        row = self._mcp_row(server_id)
        if row is None:  # pragma: no cover - guarded by callers
            raise KeyError(f"MCP server `{server_id}` was not found")
        return MCPServerConfig(
            id=row["id"],
            name=row["name"],
            transport=row["transport"],
            tool_filter=from_json(row.get("tool_filter_json"), None),
            secret_ref=row.get("grant_ref"),
        )

    def _require_mcp_client(self) -> Any:
        if self.mcp_client is None:
            raise RuntimeError(
                "no MCP transport is configured; cannot connect to or disconnect "
                "from MCP servers"
            )
        return self.mcp_client
