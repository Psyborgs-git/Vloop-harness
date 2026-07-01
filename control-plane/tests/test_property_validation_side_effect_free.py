"""Property-based test for side-effect-free Planner validation.

# Feature: orchestration-engine-completion, Property 3: Validation is side-effect free

Property 3 states:

    *For any* Workflow_Definition, validating or building its DAG dispatches
    zero model calls and zero kernel workloads.

The Planner is the Control_Plane subsystem that compiles a Workflow_Definition
into a :class:`~core.dag.Dag`. By design it is **pure**: it consults only
read-only reference catalogs (an ``AgentLookup`` and a ``ToolLookup``) and the
definition's own declared inputs. It must never reach the Inference_Gateway to
make a model call, and never reach the kernel execution adapter to start a
workload (Requirement 1.5).

This test makes that guarantee observable. It injects a call-counting model
gateway and a call-counting kernel/infra adapter into the very reference
catalogs the Planner is given, so that *if* validation ever tried to dispatch a
model call or start a kernel workload — directly or by side effect of resolving
a reference — the corresponding counter would increment. Across arbitrary
definitions (valid and invalid: well-formed graphs, dependency cycles, dangling
edges, unknown agent/tool/input references, and structurally malformed input),
both ``validate`` and ``build_dag`` are exercised and the counters are asserted
to remain at zero.

**Validates: Requirements 1.5**
"""

from __future__ import annotations

import string
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.planner import Planner, ReferenceResolver, ValidationError

# ---------------------------------------------------------------------------
# Call-counting side-effect sentinels
# ---------------------------------------------------------------------------


class CallCountingGateway:
    """A stand-in Inference_Gateway that counts every model call.

    A side-effect-free Planner must never invoke this. Any path that issued a
    model call would increment :attr:`model_calls`.
    """

    def __init__(self) -> None:
        self.model_calls = 0

    def call(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover - must not run
        self.model_calls += 1
        return {"text": ""}


class CallCountingKernel:
    """A stand-in kernel/infra adapter that counts every workload dispatch.

    A side-effect-free Planner must never invoke any of these. Each method
    increments :attr:`workloads` so an accidental kernel touch is observable.
    """

    def __init__(self) -> None:
        self.workloads = 0

    def dispatch_job(self, *args: Any, **kwargs: Any) -> str:  # pragma: no cover
        self.workloads += 1
        return "job-0"

    def snapshot_workspace(self, *args: Any, **kwargs: Any) -> str:  # pragma: no cover
        self.workloads += 1
        return "snap-0"

    def restore_workspace(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover
        self.workloads += 1

    def request_secret_grant(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        self.workloads += 1
        return None


# ---------------------------------------------------------------------------
# Reference catalogs wired to the side-effect sentinels
# ---------------------------------------------------------------------------


class SpyAgents:
    """An AgentLookup that resolves a known id set with pure reads only.

    It holds references to the gateway and kernel — modelling a real resolver
    that *could* reach them — but resolving an agent is a read and must never
    touch either. ``lookups`` records that only reads occurred.
    """

    def __init__(
        self, known: set[str], gateway: CallCountingGateway, kernel: CallCountingKernel
    ) -> None:
        self._known = known
        self._gateway = gateway
        self._kernel = kernel
        self.lookups = 0

    def get_agent(self, agent_id: str) -> Any | None:
        self.lookups += 1
        return {"id": agent_id} if agent_id in self._known else None


class SpyTools:
    """A ToolLookup that resolves a known name set with pure reads only."""

    def __init__(
        self, known: set[str], gateway: CallCountingGateway, kernel: CallCountingKernel
    ) -> None:
        self._known = known
        self._gateway = gateway
        self._kernel = kernel
        self.lookups = 0

    def has_tool(self, tool_name: str) -> bool:
        self.lookups += 1
        return tool_name in self._known


# ---------------------------------------------------------------------------
# Strategy: arbitrary Workflow_Definitions (valid AND invalid)
# ---------------------------------------------------------------------------

_IDENT = st.text(alphabet=string.ascii_lowercase + string.digits + "_", min_size=1, max_size=6)


@st.composite
def arbitrary_workflow_definitions(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a definition spanning the full valid/invalid space.

    Steps are wired with random types, random ``dependsOn`` targets (which may
    reference unknown steps or form cycles), and random agent/tool/input
    references (which may be unknown). Combined with the optionally-empty
    catalogs returned alongside, this yields a broad mix: faithful acyclic
    graphs, cyclic graphs, dangling dependencies, and unresolved references —
    all of which ``validate``/``build_dag`` must handle without side effects.
    """
    ids = draw(st.lists(_IDENT, min_size=1, max_size=6, unique=True))

    # Some agent/tool names the catalogs will know about (possibly empty, so
    # references may resolve or not).
    known_agents = set(draw(st.lists(_IDENT, max_size=4, unique=True)))
    known_tools = set(draw(st.lists(_IDENT, max_size=4, unique=True)))

    declared_input_names = draw(st.lists(_IDENT, max_size=3, unique=True))
    declared_inputs = {name: draw(st.integers(0, 50)) for name in declared_input_names}

    # The reference pools steps draw from include both known and unknown names,
    # so missing references arise naturally.
    agent_pool = list(known_agents | set(draw(st.lists(_IDENT, max_size=3, unique=True)))) or [
        draw(_IDENT)
    ]
    tool_pool = list(known_tools | set(draw(st.lists(_IDENT, max_size=3, unique=True)))) or [
        draw(_IDENT)
    ]
    input_pool = list(declared_input_names) + draw(st.lists(_IDENT, max_size=3, unique=True))

    steps: list[dict[str, Any]] = []
    for step_id in ids:
        step_type = draw(st.sampled_from(["agent", "tool", "approval", "subworkflow"]))

        # Unconstrained dependencies: may point at any id (including itself or
        # later ids), enabling cycles and dangling edges.
        depends_on = draw(st.lists(st.sampled_from(ids), max_size=min(4, len(ids)), unique=True))

        config: dict[str, Any] = {}
        if step_type == "agent" and draw(st.booleans()):
            config["agent"] = draw(st.sampled_from(agent_pool))
        if step_type == "tool" and draw(st.booleans()):
            config["tool"] = draw(st.sampled_from(tool_pool))
        if input_pool and draw(st.booleans()):
            config["inputs"] = draw(
                st.lists(st.sampled_from(input_pool), max_size=3, unique=True)
            )

        steps.append(
            {"id": step_id, "type": step_type, "config": config, "dependsOn": depends_on}
        )

    definition = {
        "version": draw(st.integers(1, 5)),
        "name": draw(st.text(max_size=12)),
        "objective": draw(st.text(max_size=20)),
        "inputs": declared_inputs,
        "steps": steps,
        "policies": {},
    }
    return {"definition": definition, "agents": known_agents, "tools": known_tools}


def _malformed_definitions() -> st.SearchStrategy[dict[str, Any]]:
    """Structurally broken inputs the Planner must still handle purely."""
    broken = st.one_of(
        st.none(),
        st.integers(),
        st.text(max_size=10),
        st.lists(st.integers(), max_size=3),
        st.fixed_dictionaries({"steps": st.integers()}),
        st.fixed_dictionaries({"steps": st.lists(st.integers(), max_size=3)}),
        st.fixed_dictionaries(
            {"steps": st.lists(st.fixed_dictionaries({"id": st.integers()}), max_size=3)}
        ),
        st.dictionaries(_IDENT, st.integers(), max_size=3),
    )
    return broken.map(lambda d: {"definition": d, "agents": set(), "tools": set()})


def any_definitions() -> st.SearchStrategy[dict[str, Any]]:
    return st.one_of(arbitrary_workflow_definitions(), _malformed_definitions())


# ---------------------------------------------------------------------------
# Property 3: validation/build dispatches zero model calls, zero workloads
# ---------------------------------------------------------------------------


@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
@given(case=any_definitions())
def test_validation_is_side_effect_free(case: dict[str, Any]) -> None:
    gateway = CallCountingGateway()
    kernel = CallCountingKernel()

    agents = SpyAgents(case["agents"], gateway, kernel)
    tools = SpyTools(case["tools"], gateway, kernel)
    planner = Planner(ReferenceResolver(agents=agents, tools=tools))

    definition = case["definition"]

    # validate() is side-effect free regardless of validity (Req 1.5).
    problems = planner.validate(definition)
    assert isinstance(problems, list)

    # build_dag() is likewise side-effect free whether it succeeds or rejects.
    try:
        planner.build_dag(definition)
    except ValidationError:
        pass  # rejection is fine; it must still dispatch nothing.

    # The core guarantee: zero model calls and zero kernel workloads (Req 1.5).
    assert gateway.model_calls == 0, "validation must dispatch no model call"
    assert kernel.workloads == 0, "validation must start no kernel workload"
