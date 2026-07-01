"""Property-based test for invocation/usage recording rules (task 11.4).

# Feature: orchestration-engine-completion, Property 15: Invocation and usage recording rules govern run continuation

Property 15 states that *for any* agent invocation:

* token usage is recorded when available;
* the run **continues** when usage recording fails **provided** the invocation
  event was recorded (Requirement 5.4); and
* the run **stops** if recording the invocation event itself fails
  (Requirement 5.6).

The test drives the DAG_Executor with a mock ``Agent_Orchestrator`` that, per
agent, behaves in one of three randomly-assigned ways:

* ``ok``         — records the invocation event **and** token usage, then
  returns a succeeded invocation. The run continues (Req 5.4 happy path).
* ``usage_fail`` — records the invocation event, then *fails* to record token
  usage but swallows that failure and still returns a succeeded invocation,
  because the invocation event was recorded (Req 5.4).
* ``event_fail`` — fails to record the invocation event and raises
  :class:`InvocationEventRecordingError`. The DAG_Executor stops the whole run
  (Req 5.6).

A run is generated as a set of independent agent steps, each backed by a unique
agent id mapped to one of the three cases, with random per-step token usage and
a random concurrency limit. The run-continuation outcome is then asserted
against the rule:

* if **any** step is ``event_fail`` the run ends ``failed`` (stopped);
* otherwise (only ``ok``/``usage_fail`` steps) the run ends ``completed``.

**Validates: Requirements 5.4, 5.6**
"""

from __future__ import annotations

import string
import threading
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.database import SQLiteBackend
from core.dag_executor import DagExecutor, InvocationEventRecordingError
from core.helpers import now_iso
from core.orchestration_types import RunState
from core.workflow_serializer import WorkflowSerializer

# ---------------------------------------------------------------------------
# Mock Agent_Orchestrator implementing the recording rule
# ---------------------------------------------------------------------------

_CASES = ("ok", "usage_fail", "event_fail")


class RecordingAgents:
    """A mock Agent_Orchestrator that models the invocation/usage rule.

    Each ``agent_id`` is mapped to a case in :data:`_CASES`. ``invoke_agent``
    records what actually happened so the property can assert the recording
    invariants of Requirements 5.4 and 5.6.
    """

    def __init__(self, cases: dict[str, str], usage: dict[str, int]) -> None:
        self._cases = cases
        self._usage = usage
        self.recorded_events: set[str] = set()
        self.recorded_usage: set[str] = set()
        self.usage_recording_failed: set[str] = set()
        self.event_recording_failed: set[str] = set()
        self._lock = threading.Lock()
        self._counter = 0

    def invoke_agent(self, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        case = self._cases[agent_id]

        # The invocation event is recorded first. If that fails the run must be
        # stopped (Req 5.6): signal it by raising InvocationEventRecordingError.
        if case == "event_fail":
            with self._lock:
                self.event_recording_failed.add(agent_id)
            raise InvocationEventRecordingError(
                f"invocation-event store unavailable for '{agent_id}'"
            )

        with self._lock:
            self.recorded_events.add(agent_id)
            self._counter += 1
            invocation_id = f"inv-{self._counter}"

        tokens = self._usage[agent_id]
        invocation_usage: dict[str, Any] | None = {"totalTokens": tokens}

        if case == "usage_fail":
            # Usage recording fails, but because the invocation event WAS
            # recorded the orchestrator swallows it and continues (Req 5.4).
            with self._lock:
                self.usage_recording_failed.add(agent_id)
            invocation_usage = None
        else:  # "ok"
            with self._lock:
                self.recorded_usage.add(agent_id)

        return {
            "id": invocation_id,
            "status": "succeeded",
            "outputJson": {"agent": agent_id},
            "usage": invocation_usage,
        }


# ---------------------------------------------------------------------------
# Strategies: random runs of independent agent steps + case assignments
# ---------------------------------------------------------------------------

_SUFFIX = st.text(alphabet=string.ascii_lowercase + string.digits, min_size=4, max_size=8)


@st.composite
def runs(draw: st.DrawFn) -> dict[str, Any]:
    """Generate an independent-step run with a per-step recording case."""
    size = draw(st.integers(min_value=1, max_value=5))
    cases: dict[str, str] = {}
    usage: dict[str, int] = {}
    steps: list[dict[str, Any]] = []
    for index in range(size):
        agent_id = f"ag-{index}"
        cases[agent_id] = draw(st.sampled_from(_CASES))
        usage[agent_id] = draw(st.integers(min_value=0, max_value=5000))
        steps.append(
            {"id": f"s{index}", "type": "agent", "config": {"agent": agent_id}}
        )
    concurrency_limit = draw(st.integers(min_value=1, max_value=5))
    return {
        "steps": steps,
        "cases": cases,
        "usage": usage,
        "concurrency_limit": concurrency_limit,
    }


def _persist_definition(
    backend: SQLiteBackend, steps: list[dict[str, Any]], definition_id: str
) -> str:
    definition = {"version": 1, "name": "wf", "steps": steps}
    ts = now_iso()
    backend.execute(
        "INSERT INTO workflow_definitions "
        "(id, name, objective, definition_json, revision, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            definition_id,
            "wf",
            "",
            WorkflowSerializer().serialize(definition),
            1,
            ts,
            ts,
        ),
    )
    return definition_id


# ---------------------------------------------------------------------------
# Property 15
# ---------------------------------------------------------------------------


# deadline=None: each example drives worker threads whose timing varies; the
# property is about run-continuation outcomes and recording invariants, not
# latency.
@settings(
    max_examples=120,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@given(case=runs())
def test_invocation_and_usage_recording_govern_run_continuation(
    case: dict[str, Any], tmp_path_factory: pytest.TempPathFactory
) -> None:
    steps: list[dict[str, Any]] = case["steps"]
    cases: dict[str, str] = case["cases"]
    usage: dict[str, int] = case["usage"]
    concurrency_limit: int = case["concurrency_limit"]

    db_path: Path = tmp_path_factory.mktemp("invrec") / "exec.db"
    backend = SQLiteBackend(db_path)
    definition_id = _persist_definition(backend, steps, "def-1")

    agents = RecordingAgents(cases, usage)
    executor = DagExecutor(
        backend, agents=agents, concurrency_limit=concurrency_limit
    )

    run_id = executor.start_run("def-1")
    final_state = executor.execute_run(run_id)

    all_agent_ids = set(cases)
    expected_stop = any(c == "event_fail" for c in cases.values())

    if expected_stop:
        # Req 5.6: a failure to record the invocation event stops the run.
        assert final_state is RunState.FAILED
        # At least one agent's invocation-event recording actually failed, and
        # for any such agent neither the event nor its usage was recorded.
        assert agents.event_recording_failed
        for agent_id, c in cases.items():
            if c == "event_fail":
                assert agent_id not in agents.recorded_events
                assert agent_id not in agents.recorded_usage
    else:
        # Req 5.4: with every invocation event recorded, the run continues to
        # completion even when token-usage recording fails for some steps.
        assert final_state is RunState.COMPLETED
        # Every invocation event was recorded for the steps that ran.
        assert agents.recorded_events == all_agent_ids
        for agent_id, c in cases.items():
            if c == "ok":
                # Usage is available and recorded (Req 5.4 happy path).
                assert agent_id in agents.recorded_usage
            else:  # "usage_fail"
                # Usage recording failed, but the event was recorded so the run
                # continued and this step still completed (Req 5.4).
                assert agent_id in agents.usage_recording_failed
                assert agent_id not in agents.recorded_usage
                assert agent_id in agents.recorded_events
