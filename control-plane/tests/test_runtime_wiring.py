"""Tests for the central orchestration wiring (task 30.10).

Covers the three deliverables of registering handlers and wiring subsystems in
bootstrap:

(a) Importing ``cp.handlers`` registers routes for every orchestration resource
    root (tools, toolsets, mcp/servers, memory, checkpoints, schedules,
    workflows). ``route()`` dispatches them to a handler without raising the
    router's "route ... was not found" ``KeyError``.
(b) The runtime exposes the accessor methods the handlers require, and a few
    happy-path delegations work against an in-memory (file-backed) database.
(c) ``resume_pending_runs()`` is invoked at startup, and a resume failure never
    propagates (Requirements 3.7, 8.5, 20.1).

The orchestration accessors are exercised through a light ``OrchestrationMixin``
harness so the tests need no Kernel gRPC stub or window manager.
"""

from __future__ import annotations

import io
import json
import tempfile
from http import HTTPStatus
from pathlib import Path
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

import cp.handlers  # noqa: F401 — triggers route registration side effects
from cp.handlers import route
from cp.orchestration import OrchestrationMixin, resume_pending_runs_at_startup
from core.database import create_database
from core.orchestration_types import ToolsetSpec, ToolSpec


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class FakeHandler:
    """Captures the JSON response written by ``write_json``."""

    def __init__(self) -> None:
        self.status: Any = None
        self.headers_sent: dict[str, str] = {}
        self.wfile = io.BytesIO()

    def send_response(self, status: Any) -> None:
        self.status = status

    def send_header(self, key: str, value: str) -> None:
        self.headers_sent[key] = value

    def end_headers(self) -> None:
        pass

    @property
    def body(self) -> Any:
        return json.loads(self.wfile.getvalue().decode("utf-8"))


class PermissiveRuntime:
    """Returns benign values for the listing accessors the GET routes call."""

    def list_tools(self, *, scope: str | None = None):
        return []

    def list_toolsets(self, *, scope: str | None = None):
        return []

    def list_mcp_servers(self):
        return []

    def list_memory_entries(self, category: str | None = None):
        return []

    def list_checkpoints(self, run_id: str):
        return []

    def list_scheduled_tasks(self, *, definition_id: str | None = None):
        return []

    def list_workflows(self):
        return []


class _Harness(OrchestrationMixin):
    """Minimal host for the OrchestrationMixin backed by a real database."""

    def __init__(self, db: Any) -> None:
        self.db = db
        self.agent_orchestrator = None
        self._init_orchestration()


def _make_harness(tmp_root: Path) -> _Harness:
    return _Harness(create_database(None, tmp_root))


# Resource roots that must resolve to a handler once cp.handlers is imported.
_GET_ROUTES = [
    "/api/v1/tools",
    "/api/v1/toolsets",
    "/api/v1/mcp/servers",
    "/api/v1/memory",
    "/api/v1/runs/run-1/checkpoints",
    "/api/v1/schedules",
    "/api/v1/workflows",
]


# ---------------------------------------------------------------------------
# (a) Route registration for every orchestration resource root
# ---------------------------------------------------------------------------


def test_all_orchestration_get_routes_register():
    runtime = PermissiveRuntime()
    for path in _GET_ROUTES:
        handler = FakeHandler()
        # A successful dispatch never raises the router's not-found KeyError.
        route(handler, "GET", path, {}, {}, runtime)
        assert handler.status == HTTPStatus.OK, path


def test_unregistered_route_still_raises_not_found():
    """Sanity check: the router does raise for a genuinely unknown path."""
    runtime = PermissiveRuntime()
    handler = FakeHandler()
    try:
        route(handler, "GET", "/api/v1/definitely-not-a-route", {}, {}, runtime)
    except KeyError as exc:
        assert "not found" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("expected a not-found KeyError for an unknown route")


# ---------------------------------------------------------------------------
# (b) Runtime exposes the accessor methods the handlers require
# ---------------------------------------------------------------------------

_REQUIRED_ACCESSORS = [
    # workflows
    "list_workflows",
    "get_workflow",
    "create_workflow",
    "validate_workflow",
    "list_workflow_templates",
    "get_workflow_template",
    "instantiate_workflow_template",
    "start_workflow_run",
    "list_workflow_runs",
    "get_workflow_run",
    "cancel_workflow_run",
    "retry_workflow_run",
    # schedules
    "list_scheduled_tasks",
    "create_scheduled_task",
    "pause_scheduled_task",
    "resume_scheduled_task",
    # memory
    "list_memory_entries",
    "record_memory_entry",
    "delete_memory_entry",
    # checkpoints
    "list_checkpoints",
    "restore_checkpoint",
    # tools
    "list_tools",
    "list_toolsets",
    "set_tool_enabled",
    "set_toolset_enabled",
    # mcp
    "list_mcp_servers",
    "configure_mcp_server",
    "get_mcp_server",
    "remove_mcp_server",
    "connect_mcp_server",
    "disconnect_mcp_server",
]


def test_runtime_exposes_all_required_accessors():
    with tempfile.TemporaryDirectory() as d:
        rt = _make_harness(Path(d))
        for name in _REQUIRED_ACCESSORS:
            assert hasattr(rt, name), f"missing accessor: {name}"
            assert callable(getattr(rt, name)), f"not callable: {name}"


def test_subsystems_constructed():
    with tempfile.TemporaryDirectory() as d:
        rt = _make_harness(Path(d))
        for attr in (
            "planner",
            "dag_executor",
            "scheduler",
            "checkpoint_manager",
            "approval_manager",
            "memory_store",
            "tool_registry",
            "provider_router",
            "workflow_events",
            "workflow_serializer",
        ):
            assert getattr(rt, attr) is not None, attr


def test_memory_accessor_happy_path():
    with tempfile.TemporaryDirectory() as d:
        rt = _make_harness(Path(d))
        entry = rt.record_memory_entry("remember this", "project")
        assert entry["content"] == "remember this"
        assert entry["category"] == "project"

        listed = rt.list_memory_entries()
        assert [e["content"] for e in listed] == ["remember this"]

        filtered = rt.list_memory_entries("project")
        assert len(filtered) == 1

        rt.delete_memory_entry(entry["id"])
        assert rt.list_memory_entries() == []


def test_workflow_accessor_happy_path():
    with tempfile.TemporaryDirectory() as d:
        rt = _make_harness(Path(d))
        # A valid (empty-steps) definition validates and persists with an id.
        result = rt.validate_workflow({"name": "Mine", "steps": []})
        assert result["valid"] is True

        workflow = rt.create_workflow({"name": "Mine", "steps": []})
        assert workflow["id"]
        assert workflow["name"] == "Mine"

        listed = rt.list_workflows()
        assert [w["id"] for w in listed] == [workflow["id"]]
        assert rt.get_workflow(workflow["id"])["name"] == "Mine"
        assert rt.get_workflow("nope") is None


def test_create_workflow_rejects_invalid_definition():
    with tempfile.TemporaryDirectory() as d:
        rt = _make_harness(Path(d))
        # A dependency cycle is rejected by the Planner as a ValueError, and no
        # definition is persisted (Requirement 1.4).
        bad = {
            "name": "cyclic",
            "steps": [
                {"id": "a", "type": "noop", "dependsOn": ["b"]},
                {"id": "b", "type": "noop", "dependsOn": ["a"]},
            ],
        }
        try:
            rt.create_workflow(bad)
        except ValueError:
            pass
        else:  # pragma: no cover - defensive
            raise AssertionError("expected ValueError for an invalid definition")
        assert rt.list_workflows() == []


def test_schedule_accessor_happy_path():
    with tempfile.TemporaryDirectory() as d:
        rt = _make_harness(Path(d))
        task = rt.create_scheduled_task("def-1", "*/5 * * * *")
        assert task["state"] == "active"
        assert task["definition_id"] == "def-1"

        listed = rt.list_scheduled_tasks()
        assert [t["id"] for t in listed] == [task["id"]]

        paused = rt.pause_scheduled_task(task["id"])
        assert paused["state"] == "paused"
        resumed = rt.resume_scheduled_task(task["id"])
        assert resumed["state"] == "active"


def test_tool_accessor_happy_path():
    with tempfile.TemporaryDirectory() as d:
        rt = _make_harness(Path(d))
        rt.tool_registry.register_toolset(
            ToolsetSpec(id="research", name="Research", tools=["web_search"])
        )
        rt.tool_registry.register_tool(
            ToolSpec(name="web_search", description="search", toolset="research")
        )

        # Without a scope the catalog is returned unresolved.
        tools = rt.list_tools()
        assert tools[0]["name"] == "web_search"
        assert "enabled" not in tools[0]

        # Enabling the tool's toolset in a scope flips the resolved flag.
        rt.set_tool_enabled("web_search", "agent-1", True)
        scoped = rt.list_tools(scope="agent-1")
        assert scoped[0]["enabled"] is True

        toolsets = rt.list_toolsets(scope="agent-1")
        assert toolsets[0]["enabled"] is True
        rt.set_toolset_enabled("research", "agent-1", False)
        assert rt.list_toolsets(scope="agent-1")[0]["enabled"] is False


def test_mcp_accessor_crud_happy_path():
    with tempfile.TemporaryDirectory() as d:
        rt = _make_harness(Path(d))
        server = rt.configure_mcp_server(
            {"name": "files", "transport": "stdio", "toolFilter": ["read"]}
        )
        assert server["name"] == "files"
        assert server["transport"] == "stdio"
        assert server["toolFilter"] == ["read"]

        listed = rt.list_mcp_servers()
        assert [s["id"] for s in listed] == [server["id"]]
        assert rt.get_mcp_server(server["id"])["name"] == "files"

        # Re-configuring the same id updates rather than duplicating.
        updated = rt.configure_mcp_server(
            {"id": server["id"], "name": "renamed", "transport": "http"}
        )
        assert updated["name"] == "renamed"
        assert len(rt.list_mcp_servers()) == 1

        rt.remove_mcp_server(server["id"])
        assert rt.get_mcp_server(server["id"]) is None


def test_checkpoint_listing_is_empty_for_unknown_run():
    with tempfile.TemporaryDirectory() as d:
        rt = _make_harness(Path(d))
        assert rt.list_checkpoints("run-x") == []


# ---------------------------------------------------------------------------
# (c) resume_pending_runs is invoked at startup and never crashes boot
# ---------------------------------------------------------------------------


class _FakeExecutor:
    def __init__(self, resumed: list[str] | None = None, raises: bool = False) -> None:
        self._resumed = resumed or []
        self._raises = raises
        self.calls: list[dict[str, Any]] = []

    def resume_pending_runs(self, *, block: bool = False) -> list[str]:
        self.calls.append({"block": block})
        if self._raises:
            raise RuntimeError("database is unavailable at boot")
        return self._resumed


def test_resume_pending_runs_invoked_at_startup():
    executor = _FakeExecutor(resumed=["run-1", "run-2"])
    resumed = resume_pending_runs_at_startup(executor)
    assert resumed == ["run-1", "run-2"]
    assert executor.calls == [{"block": False}]


def test_resume_pending_runs_swallows_failures():
    executor = _FakeExecutor(raises=True)
    # A resume failure must never propagate and block boot (Req 20.1).
    assert resume_pending_runs_at_startup(executor) == []


def test_resume_pending_runs_handles_missing_executor():
    assert resume_pending_runs_at_startup(None) == []


def test_real_dag_executor_resume_is_wired():
    """The constructed DAG_Executor exposes resume_pending_runs and runs clean."""
    with tempfile.TemporaryDirectory() as d:
        rt = _make_harness(Path(d))
        assert hasattr(rt.dag_executor, "resume_pending_runs")
        # No pending runs persisted yet, so resume returns an empty list.
        assert resume_pending_runs_at_startup(rt.dag_executor) == []


# ---------------------------------------------------------------------------
# Property: memory entries recorded through the runtime accessor all persist
# ---------------------------------------------------------------------------

# Feature: orchestration-engine-completion, Property: every Memory_Entry
# recorded through the runtime accessor is listed back (Requirement 11.1, 11.4).
# Contents are bounded so the default size budget never triggers curation.
_CONTENT = st.text(min_size=1, max_size=40)


@settings(max_examples=100, deadline=None)
@given(contents=st.lists(_CONTENT, min_size=0, max_size=12))
def test_recorded_memory_entries_round_trip(contents):
    from collections import Counter

    with tempfile.TemporaryDirectory() as d:
        rt = _make_harness(Path(d))
        for content in contents:
            rt.record_memory_entry(content)
        listed = rt.list_memory_entries()
        # Every recorded entry is listed back (order is creation-time based and
        # may tie-break by id, so compare as a multiset).
        assert Counter(e["content"] for e in listed) == Counter(contents)
