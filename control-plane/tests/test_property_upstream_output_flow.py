"""Property-based test for upstream output flow to dependents.

# Feature: orchestration-engine-completion, Property 13: Upstream outputs flow to dependents

Property 13 states that *for any* validated DAG of agent Workflow_Steps, when an
upstream step completes the DAG_Executor makes that step's output available as
input to every dependent step, keyed by the upstream (dependency) step id
(Requirement 5.2).

The test generates random *acyclic* agent-step Workflow_Definitions (unique step
ids, ``dependsOn`` referencing only strictly-earlier steps so the graph is
acyclic with no dangling edges), assigns each step its own agent id, and drives a
real run on a fresh temp SQLite backend. A mock Agent_Orchestrator returns a
per-step *distinctive* output and records the ``inputs`` mapping each step's
invocation received.

After the run reaches a terminal ``completed`` state, the test asserts that for
every dependent step and every one of its dependency step ids, the inputs that
step received contained — keyed by that dependency's step id — exactly the
output the dependency produced.

**Validates: Requirements 5.2**
"""

from __future__ import annotations

import copy
import string
import threading
import uuid
from pathlib import Path
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.database import SQLiteBackend
from core.dag_executor import DagExecutor
from core.helpers import now_iso
from core.orchestration_types import RunState
from core.workflow_serializer import WorkflowSerializer

# ---------------------------------------------------------------------------
# Strategy: random acyclic agent-step definitions + a concurrency limit
# ---------------------------------------------------------------------------

_IDENT = st.text(
    alphabet=string.ascii_letters + string.digits + "_", min_size=1, max_size=6
)

_AGENT_PREFIX = "agent::"


def _agent_id_for(step_id: str) -> str:
    """The agent id a step is configured to invoke (1:1 with the step id)."""
    return f"{_AGENT_PREFIX}{step_id}"


def _step_id_from_agent(agent_id: str) -> str:
    """Recover the step id encoded in an agent id."""
    return agent_id[len(_AGENT_PREFIX) :]


def _output_for(step_id: str) -> dict[str, Any]:
    """A distinctive, deterministic output produced by ``step_id``.

    Distinctive because step ids are unique, so two different dependencies can
    never produce the same output — letting the assertion confirm that *exactly*
    the right dependency's output flowed to each dependent.
    """
    return {"source": step_id, "marker": f"output-of-{step_id}"}


@st.composite
def agent_dags(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a random ACYCLIC agent-step definition + a concurrency limit.

    Acyclicity is constructed by design: step ids are unique, and step ``i``'s
    ``dependsOn`` is drawn only from the ids of strictly-earlier steps, so the
    dependency graph can contain no cycle and no dangling edge.
    """
    ids = draw(st.lists(_IDENT, min_size=1, max_size=7, unique=True))

    steps: list[dict[str, Any]] = []
    for index, step_id in enumerate(ids):
        if index > 0:
            depends_on = draw(
                st.lists(
                    st.sampled_from(ids[:index]),
                    max_size=min(3, index),
                    unique=True,
                )
            )
        else:
            depends_on = []
        steps.append(
            {
                "id": step_id,
                "type": "agent",
                "config": {"agent": _agent_id_for(step_id)},
                "dependsOn": depends_on,
            }
        )

    definition = {
        "version": 1,
        "name": "wf",
        "objective": "",
        "inputs": {},
        "steps": steps,
        "policies": {},
    }
    concurrency_limit = draw(st.integers(min_value=1, max_value=6))
    return {"definition": definition, "concurrency_limit": concurrency_limit}


# ---------------------------------------------------------------------------
# Mock Agent_Orchestrator: distinctive output + records received inputs
# ---------------------------------------------------------------------------


class _RecordingAgents:
    """A thread-safe mock Agent_Orchestrator.

    Each invocation returns a per-step distinctive output (so the dependent's
    inputs can be matched back to the exact producing dependency) and records,
    per step id, a deep copy of the ``inputs`` mapping the invocation received.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.received_inputs: dict[str, dict[str, Any]] = {}

    def invoke_agent(self, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        step_id = _step_id_from_agent(agent_id)
        with self._lock:
            # Deep-copy so later mutation of the payload can't corrupt the record.
            self.received_inputs[step_id] = copy.deepcopy(
                dict(payload.get("inputs", {}))
            )
        return {
            "id": f"inv-{step_id}",
            "status": "succeeded",
            "outputJson": _output_for(step_id),
        }


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _persist_definition(
    backend: SQLiteBackend, definition: dict[str, Any], definition_id: str
) -> None:
    ts = now_iso()
    backend.execute(
        "INSERT INTO workflow_definitions "
        "(id, name, objective, definition_json, revision, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            definition_id,
            definition.get("name", "wf"),
            definition.get("objective", ""),
            WorkflowSerializer().serialize(definition),
            1,
            ts,
            ts,
        ),
    )


# ---------------------------------------------------------------------------
# Property 13: Upstream outputs flow to dependents
# ---------------------------------------------------------------------------


# deadline=None: each example does real temp-SQLite I/O and spins up worker
# threads, so per-example timing varies; the property is about input flow, not
# latency.
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(case=agent_dags())
def test_upstream_outputs_flow_to_dependents(
    case: dict[str, Any], tmp_path_factory
) -> None:
    definition = case["definition"]
    concurrency_limit = case["concurrency_limit"]

    deps_by_step = {
        step["id"]: tuple(step["dependsOn"]) for step in definition["steps"]
    }

    db_dir: Path = tmp_path_factory.mktemp("upstream-output-flow")
    backend = SQLiteBackend(db_dir / f"exec-{uuid.uuid4().hex}.db")

    definition_id = f"def-{uuid.uuid4().hex}"
    _persist_definition(backend, definition, definition_id)

    agents = _RecordingAgents()
    executor = DagExecutor(
        backend,
        agents=agents,
        concurrency_limit=concurrency_limit,
    )

    run_id = executor.start_run(definition_id, concurrency_limit=concurrency_limit)
    final = executor.execute_run(run_id, timeout=30)

    # Every agent step succeeds, so the run must complete (and thus every step
    # was dispatched and its inputs recorded).
    assert final is RunState.COMPLETED

    # Req 5.2: every dependent step received, keyed by each of its dependency
    # step ids, exactly that dependency's produced output.
    for step_id, deps in deps_by_step.items():
        received = agents.received_inputs[step_id]
        for dep in deps:
            assert dep in received, (
                f"step '{step_id}' did not receive input keyed by dependency "
                f"'{dep}'"
            )
            assert received[dep] == _output_for(dep), (
                f"step '{step_id}' received the wrong output for dependency "
                f"'{dep}'"
            )
