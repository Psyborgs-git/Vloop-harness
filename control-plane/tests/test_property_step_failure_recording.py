"""Property-based test for step-failure recording (task 11.3).

# Feature: orchestration-engine-completion, Property 14: Step failure marks the step failed and records the reason

Property 14 states that *for any* agent Workflow_Step that fails — whether the
agent invocation runs and reports ``status=failed`` with an error message, or a
pre-execution error occurs (a missing agent reference) before the invocation
begins — the DAG_Executor:

* sets that step's persisted state to ``failed`` (Requirement 5.3), with the
  step's ``error_message`` equal to the failure reason; and
* records that same failure reason in the Workflow_Run event history
  (``workflow_events``) attributed to the step.

The test drives the DAG_Executor with a mock ``Agent_Orchestrator`` over a run
of independent agent steps, each randomly assigned one of three behaviours:

* ``ok``      — the agent invocation succeeds; the step completes.
* ``fail``    — the agent invocation runs and returns ``status=failed`` with a
  *distinctive random* ``errorMessage``; that message is the step's reason.
* ``preexec`` — the step is configured without an agent reference, so a
  pre-execution error occurs before any invocation; the reason is the
  executor's descriptive pre-execution message.

Every example contains at least one failing step. For each failing step the
property asserts the persisted state is ``failed``, the persisted
``error_message`` equals the step's reason, and an event attributed to that
step carries the same reason in the run event history.

**Validates: Requirements 5.3**
"""

from __future__ import annotations

import string
import threading
import uuid
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.database import SQLiteBackend
from core.dag_executor import DagExecutor
from core.event_router import WorkflowEventType
from core.helpers import now_iso
from core.orchestration_types import RunState, StepState
from core.workflow_serializer import WorkflowSerializer

# The fixed pre-execution reason the executor records for an agent step that is
# missing its agent reference (Requirement 5.3 pre-execution branch).
_PREEXEC_REASON = "agent step is missing an agent reference"

_CASES = ("ok", "fail", "preexec")


# ---------------------------------------------------------------------------
# Mock Agent_Orchestrator
# ---------------------------------------------------------------------------


class FailingAgents:
    """A mock Agent_Orchestrator over a fixed set of agent ids.

    ``fail_reasons`` maps an agent id to the distinctive ``errorMessage`` its
    invocation reports (modelling a *failed* invocation, Req 5.3). Any other
    known agent id succeeds. Agent ids for ``preexec`` steps are never
    registered because those steps fail before an invocation is dispatched.
    """

    def __init__(self, fail_reasons: dict[str, str]) -> None:
        self._fail_reasons = fail_reasons
        self.calls: list[str] = []
        self._lock = threading.Lock()
        self._counter = 0

    def invoke_agent(self, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self.calls.append(agent_id)
            self._counter += 1
            invocation_id = f"inv-{self._counter}"
        if agent_id in self._fail_reasons:
            return {
                "id": invocation_id,
                "status": "failed",
                "errorMessage": self._fail_reasons[agent_id],
            }
        return {
            "id": invocation_id,
            "status": "succeeded",
            "outputJson": {"agent": agent_id},
        }


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_REASON_TEXT = st.text(
    alphabet=string.ascii_letters + string.digits + " _-", min_size=1, max_size=24
)


@st.composite
def runs(draw: st.DrawFn) -> dict[str, Any]:
    """Generate an independent-step run with at least one failing step.

    Each step is assigned one of ``_CASES``. A failing step (``fail`` or
    ``preexec``) carries the reason expected to be both persisted on the step
    and recorded in the run event history.
    """
    size = draw(st.integers(min_value=1, max_value=6))
    kinds = [draw(st.sampled_from(_CASES)) for _ in range(size)]
    # Guarantee at least one failing step so the property is non-vacuous.
    if not any(kind in ("fail", "preexec") for kind in kinds):
        kinds[draw(st.integers(min_value=0, max_value=size - 1))] = draw(
            st.sampled_from(("fail", "preexec"))
        )

    steps: list[dict[str, Any]] = []
    fail_reasons: dict[str, str] = {}
    # step_id -> ("ok"|"failed", reason|None)
    expectations: dict[str, tuple[str, str | None]] = {}

    for index, kind in enumerate(kinds):
        step_id = f"s{index}"
        if kind == "preexec":
            # No agent reference -> pre-execution error before any invocation.
            steps.append({"id": step_id, "type": "agent", "config": {}})
            expectations[step_id] = ("failed", _PREEXEC_REASON)
            continue

        agent_id = f"ag-{index}"
        steps.append({"id": step_id, "type": "agent", "config": {"agent": agent_id}})
        if kind == "fail":
            # Distinctive, per-step-unique reason so the per-step assertions on
            # persisted error_message and event history are unambiguous.
            reason = f"REASON-{index}-{draw(_REASON_TEXT)}-{uuid.uuid4().hex[:8]}"
            fail_reasons[agent_id] = reason
            expectations[step_id] = ("failed", reason)
        else:  # "ok"
            expectations[step_id] = ("ok", None)

    return {
        "steps": steps,
        "fail_reasons": fail_reasons,
        "expectations": expectations,
        "concurrency_limit": draw(st.integers(min_value=1, max_value=5)),
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
# Property 14
# ---------------------------------------------------------------------------


# deadline=None: each example drives worker threads whose timing varies; the
# property is about recorded failure state/reason, not latency.
@settings(
    max_examples=120,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@given(case=runs())
def test_step_failure_marks_step_failed_and_records_reason(
    case: dict[str, Any], tmp_path_factory: pytest.TempPathFactory
) -> None:
    steps: list[dict[str, Any]] = case["steps"]
    fail_reasons: dict[str, str] = case["fail_reasons"]
    expectations: dict[str, tuple[str, str | None]] = case["expectations"]
    concurrency_limit: int = case["concurrency_limit"]

    db_path: Path = tmp_path_factory.mktemp("stepfail") / "exec.db"
    backend = SQLiteBackend(db_path)
    _persist_definition(backend, steps, "def-1")

    agents = FailingAgents(fail_reasons)
    executor = DagExecutor(
        backend, agents=agents, concurrency_limit=concurrency_limit
    )

    run_id = executor.start_run("def-1")
    final_state = executor.execute_run(run_id)

    # At least one step fails, so the run as a whole ends ``failed``.
    assert final_state is RunState.FAILED

    run = executor.get_run(run_id)
    steps_by_id = {row["step_id"]: row for row in run["steps"]}
    events = run["events"]

    for step_id, (kind, reason) in expectations.items():
        step = steps_by_id[step_id]
        if kind == "ok":
            assert step["state"] == StepState.COMPLETED.value
            continue

        # Req 5.3: the failing step's persisted state is ``failed`` and its
        # error_message is exactly the failure reason.
        assert step["state"] == StepState.FAILED.value
        assert step["error_message"] == reason

        # Req 5.3: the reason is recorded in the run event history, attributed
        # to the failing step via a step.state_changed event.
        recorded = [
            event
            for event in events
            if event["step_id"] == step_id
            and event["type"] == WorkflowEventType.STEP_STATE_CHANGED
            and event["payload"].get("state") == StepState.FAILED.value
            and event["payload"].get("error_message") == reason
        ]
        assert recorded, (
            f"failure reason for step '{step_id}' not found in run event history"
        )
