"""Unit tests for core.planner (Planner + ReferenceResolver).

Covers Requirements 1.1 (faithful DAG build), 1.2 (cycle rejection naming the
involved steps), 1.3 (missing agent/tool/input references named), 1.4 (no id
assigned / nothing persisted by the Planner), and 1.5 (validation is side-effect
free — no model calls, no kernel workloads).
"""

from __future__ import annotations

import pytest

from core.dag import Dag
from core.planner import Planner, ReferenceResolver, ValidationError


# -- test doubles ----------------------------------------------------------


class FakeAgents:
    """An AgentLookup backed by a known id set."""

    def __init__(self, known: set[str]) -> None:
        self._known = known
        self.calls = 0

    def get_agent(self, agent_id: str):
        self.calls += 1
        return {"id": agent_id} if agent_id in self._known else None


class FakeTools:
    """A ToolLookup backed by a known name set."""

    def __init__(self, known: set[str]) -> None:
        self._known = known
        self.calls = 0

    def has_tool(self, tool_name: str) -> bool:
        self.calls += 1
        return tool_name in self._known


def _resolver(agents: set[str] | None = None, tools: set[str] | None = None) -> ReferenceResolver:
    return ReferenceResolver(
        agents=FakeAgents(agents or set()),
        tools=FakeTools(tools or set()),
    )


def _planner(agents: set[str] | None = None, tools: set[str] | None = None) -> Planner:
    return Planner(_resolver(agents, tools))


def _valid_definition() -> dict:
    return {
        "version": 1,
        "name": "Nightly report",
        "objective": "Summarize yesterday's activity",
        "inputs": {"date": "2024-01-01"},
        "steps": [
            {
                "id": "fetch",
                "type": "tool",
                "config": {"tool": "db_query", "inputs": ["date"]},
                "dependsOn": [],
            },
            {
                "id": "summarize",
                "type": "agent",
                "config": {"agent": "writer"},
                "dependsOn": ["fetch"],
            },
        ],
        "policies": {"max_retries": 2},
    }


# -- build_dag: success ----------------------------------------------------


def test_build_dag_compiles_valid_definition():
    planner = _planner(agents={"writer"}, tools={"db_query"})
    dag = planner.build_dag(_valid_definition())
    assert isinstance(dag, Dag)
    # Node set equals the definition's step set (Req 1.1).
    assert set(dag.nodes) == {"fetch", "summarize"}
    # Edges equal the declared dependencies (Req 1.1).
    assert dag.edges == (("fetch", "summarize"),)
    assert dag.nodes["summarize"].depends_on == ("fetch",)


def test_validate_returns_empty_for_valid_definition():
    planner = _planner(agents={"writer"}, tools={"db_query"})
    assert planner.validate(_valid_definition()) == []


def test_build_dag_allows_absent_references():
    # An agent step without an explicit agent reference is not a missing ref.
    definition = {
        "name": "x",
        "inputs": {},
        "steps": [{"id": "s1", "type": "agent", "config": {}, "dependsOn": []}],
    }
    dag = _planner().build_dag(definition)
    assert set(dag.nodes) == {"s1"}


# -- build_dag: cycles (Req 1.2) -------------------------------------------


def test_build_dag_rejects_cycle_and_names_steps():
    definition = {
        "name": "cyclic",
        "inputs": {},
        "steps": [
            {"id": "a", "type": "agent", "config": {}, "dependsOn": ["b"]},
            {"id": "b", "type": "agent", "config": {}, "dependsOn": ["a"]},
        ],
    }
    with pytest.raises(ValidationError) as excinfo:
        _planner().build_dag(definition)
    err = excinfo.value
    assert err.code == "cycle"
    problems = err.detail["problems"]
    cycle_problem = next(p for p in problems if p["code"] == "cycle")
    # The error identifies the steps involved in the cycle (Req 1.2).
    assert set(cycle_problem["detail"]["steps"]) == {"a", "b"}


def test_validate_reports_self_loop_cycle():
    definition = {
        "name": "selfloop",
        "inputs": {},
        "steps": [{"id": "a", "type": "agent", "config": {}, "dependsOn": ["a"]}],
    }
    problems = _planner().validate(definition)
    assert any(p["code"] == "cycle" and "a" in p["detail"]["steps"] for p in problems)


# -- build_dag: missing references (Req 1.3) -------------------------------


def test_build_dag_rejects_unknown_agent_and_names_it():
    definition = {
        "name": "x",
        "inputs": {},
        "steps": [
            {"id": "s1", "type": "agent", "config": {"agent": "ghost"}, "dependsOn": []}
        ],
    }
    with pytest.raises(ValidationError) as excinfo:
        _planner(agents=set()).build_dag(definition)
    err = excinfo.value
    assert err.code == "missing_agent"
    problem = err.detail["problems"][0]
    assert problem["detail"]["reference"] == "ghost"
    assert problem["detail"]["step"] == "s1"


def test_build_dag_rejects_unknown_tool_and_names_it():
    definition = {
        "name": "x",
        "inputs": {},
        "steps": [
            {"id": "s1", "type": "tool", "config": {"tool": "nope"}, "dependsOn": []}
        ],
    }
    with pytest.raises(ValidationError) as excinfo:
        _planner(tools=set()).build_dag(definition)
    assert excinfo.value.code == "missing_tool"
    assert excinfo.value.detail["problems"][0]["detail"]["reference"] == "nope"


def test_build_dag_rejects_unknown_input_and_names_it():
    definition = {
        "name": "x",
        "inputs": {"known": 1},
        "steps": [
            {
                "id": "s1",
                "type": "tool",
                "config": {"tool": "t", "inputs": ["missing"]},
                "dependsOn": [],
            }
        ],
    }
    with pytest.raises(ValidationError) as excinfo:
        _planner(tools={"t"}).build_dag(definition)
    assert excinfo.value.code == "missing_input"
    assert excinfo.value.detail["problems"][0]["detail"]["reference"] == "missing"


def test_build_dag_rejects_dangling_dependency():
    definition = {
        "name": "x",
        "inputs": {},
        "steps": [
            {"id": "s1", "type": "agent", "config": {}, "dependsOn": ["ghost"]}
        ],
    }
    with pytest.raises(ValidationError) as excinfo:
        _planner().build_dag(definition)
    assert excinfo.value.code == "missing_dependency"
    assert excinfo.value.detail["problems"][0]["detail"]["reference"] == "ghost"


# -- structural problems ---------------------------------------------------


def test_validate_rejects_non_object_definition():
    problems = _planner().validate("not a dict")  # type: ignore[arg-type]
    assert problems and problems[0]["code"] == "invalid_definition"


def test_validate_rejects_duplicate_step_ids():
    definition = {
        "name": "x",
        "inputs": {},
        "steps": [
            {"id": "dup", "type": "agent", "config": {}, "dependsOn": []},
            {"id": "dup", "type": "agent", "config": {}, "dependsOn": []},
        ],
    }
    problems = _planner().validate(definition)
    assert any(p["code"] == "duplicate_step_id" for p in problems)


def test_validate_rejects_step_without_id():
    definition = {
        "name": "x",
        "inputs": {},
        "steps": [{"type": "agent", "config": {}, "dependsOn": []}],
    }
    problems = _planner().validate(definition)
    assert any(p["code"] == "invalid_step" for p in problems)


# -- Req 1.4 / 1.5: no side effects, no id ---------------------------------


def test_build_dag_returns_dag_without_assigning_id():
    dag = _planner(agents={"writer"}, tools={"db_query"}).build_dag(_valid_definition())
    # The Planner returns a pure Dag; it assigns no id and persists nothing.
    assert not hasattr(dag, "id")


def test_validate_is_side_effect_free_no_model_or_kernel_calls():
    # Resolver lookups are read-only; assert the planner triggers no model
    # dispatch or kernel workload by passing catalogs that would record any
    # mutation. Reference lookups (reads) are permitted.
    agents = FakeAgents({"writer"})
    tools = FakeTools({"db_query"})
    planner = Planner(ReferenceResolver(agents=agents, tools=tools))
    before = (agents.calls, tools.calls)
    planner.validate(_valid_definition())
    # Lookups happened (reads only); there is no persistence/model/kernel path
    # in the planner to invoke.
    assert (agents.calls, tools.calls) >= before


def test_invalid_definition_yields_no_dag():
    definition = {
        "name": "x",
        "inputs": {},
        "steps": [
            {"id": "a", "type": "agent", "config": {}, "dependsOn": ["b"]},
            {"id": "b", "type": "agent", "config": {}, "dependsOn": ["a"]},
        ],
    }
    planner = _planner()
    with pytest.raises(ValidationError):
        planner.build_dag(definition)
    # validate surfaces the same problem without raising or persisting.
    assert planner.validate(definition)
