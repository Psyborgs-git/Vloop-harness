"""Property-based test for invalid-definition rejection by the Planner.

# Feature: orchestration-engine-completion, Property 2: Invalid definitions (cycles and missing references) are rejected and named

Property 2 states:

    *For any* Workflow_Definition containing a dependency cycle, the Planner
    rejects it with an error identifying the steps in the cycle; *for any*
    definition referencing a non-existent agent, tool, or input, the Planner
    rejects it with an error naming the missing reference; in both cases the
    definition is left unpersisted and without an id.

The Planner has no persistence path and assigns no identifier, so the
"unpersisted / no id" half is established structurally: ``build_dag`` raises
``ValidationError`` (returning no ``Dag`` and therefore no id), and ``validate``
surfaces the same problems without side effects.

**Validates: Requirements 1.2, 1.3**
"""

from __future__ import annotations

import string

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.planner import Planner, ReferenceResolver, ValidationError

# ---------------------------------------------------------------------------
# Test doubles — empty/known reference catalogs
# ---------------------------------------------------------------------------


class FakeAgents:
    """An AgentLookup backed by a known id set (read-only)."""

    def __init__(self, known: set[str]) -> None:
        self._known = known

    def get_agent(self, agent_id: str):
        return {"id": agent_id} if agent_id in self._known else None


class FakeTools:
    """A ToolLookup backed by a known name set (read-only)."""

    def __init__(self, known: set[str]) -> None:
        self._known = known

    def has_tool(self, tool_name: str) -> bool:
        return tool_name in self._known


def _planner(agents: set[str], tools: set[str]) -> Planner:
    return Planner(ReferenceResolver(agents=FakeAgents(agents), tools=FakeTools(tools)))


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Non-empty lowercase identifiers used for step ids and reference names.
_identifiers = st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=6)


@st.composite
def cyclic_definitions(draw: st.DrawFn) -> dict:
    """(a) Definitions with an injected dependency cycle.

    Generates two or more distinct steps wired into a closed dependency ring
    (each step depends on the next, the last wraps back to the first). Steps
    carry empty configs so no agent/tool/input reference problem can mask the
    cycle — the cycle is therefore the primary (and only) problem.
    """
    ids = draw(
        st.lists(_identifiers, min_size=2, max_size=6, unique=True)
    )
    n = len(ids)
    steps = [
        {
            "id": sid,
            "type": "agent",
            "config": {},
            "dependsOn": [ids[(i + 1) % n]],
        }
        for i, sid in enumerate(ids)
    ]
    return {
        "kind": "cycle",
        "definition": {
            "name": "cyclic",
            "inputs": {},
            "steps": steps,
            "policies": {},
        },
        "agents": set(),
        "tools": set(),
        "ring": set(ids),
    }


@st.composite
def missing_reference_definitions(draw: st.DrawFn) -> dict:
    """(b) Definitions referencing a non-existent agent, tool, or input.

    Generates a single offending step whose reference cannot be resolved by an
    empty catalog (agent/tool) or an empty declared-inputs map (input). The
    missing reference is the only problem, so it drives the raised error code.
    """
    kind = draw(st.sampled_from(["agent", "tool", "input"]))
    step_id = draw(_identifiers)
    missing = draw(_identifiers)

    if kind == "agent":
        definition = {
            "name": "missing-agent",
            "inputs": {},
            "steps": [
                {
                    "id": step_id,
                    "type": "agent",
                    "config": {"agent": missing},
                    "dependsOn": [],
                }
            ],
            "policies": {},
        }
        return {
            "kind": "missing",
            "definition": definition,
            "agents": set(),
            "tools": set(),
            "expect_code": "missing_agent",
            "reference": missing,
            "step": step_id,
        }

    if kind == "tool":
        definition = {
            "name": "missing-tool",
            "inputs": {},
            "steps": [
                {
                    "id": step_id,
                    "type": "tool",
                    "config": {"tool": missing},
                    "dependsOn": [],
                }
            ],
            "policies": {},
        }
        return {
            "kind": "missing",
            "definition": definition,
            "agents": set(),
            "tools": set(),
            "expect_code": "missing_tool",
            "reference": missing,
            "step": step_id,
        }

    # kind == "input": the referenced tool is known, but the input is not
    # declared (declared inputs are empty), so the only problem is the input.
    known_tool = "known_tool"
    definition = {
        "name": "missing-input",
        "inputs": {},
        "steps": [
            {
                "id": step_id,
                "type": "tool",
                "config": {"tool": known_tool, "inputs": [missing]},
                "dependsOn": [],
            }
        ],
        "policies": {},
    }
    return {
        "kind": "missing",
        "definition": definition,
        "agents": set(),
        "tools": {known_tool},
        "expect_code": "missing_input",
        "reference": missing,
        "step": step_id,
    }


def invalid_definitions() -> st.SearchStrategy[dict]:
    """Either a cyclic definition or a missing-reference definition."""
    return st.one_of(cyclic_definitions(), missing_reference_definitions())


# ---------------------------------------------------------------------------
# Property 2: Invalid definitions are rejected and named
# ---------------------------------------------------------------------------


@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
@given(case=invalid_definitions())
def test_invalid_definitions_are_rejected_and_named(case: dict) -> None:
    planner = _planner(agents=case["agents"], tools=case["tools"])
    definition = case["definition"]

    # build_dag rejects the definition with a ValidationError (Req 1.2, 1.3).
    with pytest.raises(ValidationError) as excinfo:
        planner.build_dag(definition)
    err = excinfo.value
    problems = err.detail["problems"]
    assert problems, "ValidationError must carry the problems it found"

    if case["kind"] == "cycle":
        # The error identifies the steps involved in the cycle (Req 1.2).
        assert err.code == "cycle"
        cycle_problems = [p for p in problems if p["code"] == "cycle"]
        assert cycle_problems, "a cycle problem must be reported"
        named = set(cycle_problems[0]["detail"]["steps"])
        assert named, "cycle problem must name the steps involved"
        assert named <= case["ring"], "named cycle steps must be real steps in the ring"
    else:
        # The error names the missing reference and the offending step (Req 1.3).
        assert err.code == case["expect_code"]
        matching = [
            p
            for p in problems
            if p["code"] == case["expect_code"]
            and p["detail"].get("reference") == case["reference"]
        ]
        assert matching, "missing-reference problem must name the offending reference"
        assert matching[0]["detail"]["step"] == case["step"]

    # Nothing is persisted and no id is assigned: build_dag returned no Dag
    # (it raised), and validate surfaces the same problems side-effect free.
    assert planner.validate(definition), "validate must report the same problems"
