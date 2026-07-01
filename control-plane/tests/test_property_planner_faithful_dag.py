"""Property-based test for faithful DAG build and id assignment.

# Feature: orchestration-engine-completion, Property 1: Planner builds a faithful DAG for valid definitions and assigns an id only then

Property 1 states that for any *valid* Workflow_Definition, ``build_dag``
produces a DAG whose node set equals the definition's step ids and whose edges
equal the declared dependencies (Requirement 1.1), and the Control_Plane
assigns a unique identifier — but only because validation passed
(Requirement 1.4).

The Planner itself assigns no id and persists nothing; it returns a ``Dag`` on
success and raises ``ValidationError`` otherwise. The "an id is assigned only
on validity" half of Requirement 1.4 is modelled here with a small caller
wrapper (:class:`PersistingCaller`) that mirrors the real HTTP handler: it
calls ``build_dag`` first and assigns a fresh unique id (and persists) *only*
when the build succeeds. This test exercises the positive case — every valid
definition yields a faithful DAG and a freshly assigned, unique id — while the
negative case (invalid definitions get no id) is covered by Property 2.

**Validates: Requirements 1.1, 1.4**
"""

from __future__ import annotations

import string
import uuid
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.dag import Dag
from core.planner import Planner, ReferenceResolver, ValidationError

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class KnownAgents:
    """An AgentLookup that resolves exactly the agent ids it was told about."""

    def __init__(self, known: set[str]) -> None:
        self._known = known

    def get_agent(self, agent_id: str) -> Any | None:
        return {"id": agent_id} if agent_id in self._known else None


class KnownTools:
    """A ToolLookup that resolves exactly the tool names it was told about."""

    def __init__(self, known: set[str]) -> None:
        self._known = known

    def has_tool(self, tool_name: str) -> bool:
        return tool_name in self._known


class PersistingCaller:
    """Models the HTTP handler: assigns an id and persists ONLY on success.

    This wraps the (pure, id-less) Planner. ``submit`` builds the DAG first; an
    invalid definition raises out of ``build_dag`` before any id is minted or
    anything is stored, so an identifier is assigned only to definitions that
    pass validation (Requirement 1.4).
    """

    def __init__(self, planner: Planner) -> None:
        self._planner = planner
        self.persisted: dict[str, Dag] = {}

    def submit(self, definition: dict[str, Any]) -> tuple[str, Dag]:
        dag = self._planner.build_dag(definition)  # raises ValidationError if invalid
        workflow_id = str(uuid.uuid4())
        self.persisted[workflow_id] = dag
        return workflow_id, dag


# ---------------------------------------------------------------------------
# Strategy: valid Workflow_Definitions
# ---------------------------------------------------------------------------

_IDENT = st.text(alphabet=string.ascii_letters + string.digits + "_", min_size=1, max_size=8)


@st.composite
def valid_workflow_definitions(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a *valid* Workflow_Definition plus the catalogs that resolve it.

    Validity is constructed by design:

    * step ids are unique, non-empty strings;
    * ``dependsOn`` of step ``i`` is a subset of the ids of *earlier* steps, so
      the dependency graph is acyclic and has no dangling edges;
    * every agent/tool reference and every consumed input is registered in the
      returned catalogs / declared inputs, so all references resolve.

    Returns the definition under a ``"definition"`` key alongside the
    ``"agents"`` and ``"tools"`` sets the ReferenceResolver must know.
    """
    ids = draw(st.lists(_IDENT, min_size=1, max_size=6, unique=True))

    # Declared top-level inputs the steps may consume.
    input_names = draw(st.lists(_IDENT, max_size=4, unique=True))
    declared_inputs = {name: draw(st.integers(min_value=0, max_value=100)) for name in input_names}

    agents: set[str] = set()
    tools: set[str] = set()
    steps: list[dict[str, Any]] = []

    for index, step_id in enumerate(ids):
        step_type = draw(st.sampled_from(["agent", "tool", "approval", "subworkflow"]))

        # Acyclic by construction: only depend on strictly-earlier steps.
        if index > 0:
            depends_on = draw(
                st.lists(st.sampled_from(ids[:index]), max_size=min(3, index), unique=True)
            )
        else:
            depends_on = []

        config: dict[str, Any] = {}
        if step_type == "agent" and draw(st.booleans()):
            agent_ref = draw(_IDENT)
            agents.add(agent_ref)
            config["agent"] = agent_ref
        elif step_type == "tool" and draw(st.booleans()):
            tool_ref = draw(_IDENT)
            tools.add(tool_ref)
            config["tool"] = tool_ref

        if input_names:
            consumed = draw(st.lists(st.sampled_from(input_names), max_size=3, unique=True))
            if consumed:
                config["inputs"] = consumed

        steps.append(
            {
                "id": step_id,
                "type": step_type,
                "config": config,
                "dependsOn": depends_on,
            }
        )

    definition = {
        "version": draw(st.integers(min_value=1, max_value=10)),
        "name": draw(st.text(max_size=20)),
        "objective": draw(st.text(max_size=40)),
        "inputs": declared_inputs,
        "steps": steps,
        "policies": {},
    }
    return {"definition": definition, "agents": agents, "tools": tools}


def _expected_edges(definition: dict[str, Any]) -> set[tuple[str, str]]:
    """The declared dependency edges as ``(from, to)`` pairs."""
    node_ids = {step["id"] for step in definition["steps"]}
    edges: set[tuple[str, str]] = set()
    for step in definition["steps"]:
        for dep in step["dependsOn"]:
            if dep in node_ids:
                edges.add((dep, step["id"]))
    return edges


# ---------------------------------------------------------------------------
# Property 1: faithful DAG build + id-only-on-validity
# ---------------------------------------------------------------------------


@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
@given(case=valid_workflow_definitions())
def test_planner_builds_faithful_dag_and_assigns_id_only_on_validity(case: dict[str, Any]) -> None:
    definition = case["definition"]
    planner = Planner(
        ReferenceResolver(
            agents=KnownAgents(case["agents"]),
            tools=KnownTools(case["tools"]),
        )
    )

    # The Planner itself must never raise for a valid definition and never
    # mutate/persist or attach an id to the returned Dag.
    dag = planner.build_dag(definition)
    assert isinstance(dag, Dag)
    assert not hasattr(dag, "id")  # Planner assigns no id (Req 1.4).

    # Faithful DAG: node set equals the definition's step ids (Req 1.1).
    expected_nodes = {step["id"] for step in definition["steps"]}
    assert set(dag.nodes) == expected_nodes

    # Faithful DAG: edges equal the declared dependencies (Req 1.1).
    assert set(dag.edges) == _expected_edges(definition)

    # validate() agrees the definition is valid and is side-effect free wrt ids.
    assert planner.validate(definition) == []

    # An id is assigned only because validation passed (Req 1.4). The caller
    # wrapper mints an id and persists strictly after build_dag succeeds.
    caller = PersistingCaller(planner)
    first_id, persisted_dag = caller.submit(definition)
    assert first_id  # a unique identifier was assigned on success
    assert persisted_dag is dag or set(persisted_dag.nodes) == expected_nodes
    assert first_id in caller.persisted

    # Uniqueness: a second successful submission yields a distinct id.
    second_id, _ = caller.submit(definition)
    assert second_id != first_id
    assert set(caller.persisted) == {first_id, second_id}
