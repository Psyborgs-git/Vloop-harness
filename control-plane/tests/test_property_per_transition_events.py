"""Property-based test for per-transition workflow events.

# Feature: orchestration-engine-completion, Property 10: Every step transition emits a corresponding event

Property 10 states that *for any* sequence of Workflow_Step state transitions,
the Event_Router emits exactly one corresponding event per transition, each
carrying the run identifier.

This test drives a sequence of step state transitions through
:class:`core.event_router.EventRouter`, emitting one
``WorkflowEventType.STEP_STATE_CHANGED`` event per transition, then asserts that
the *persisted* ``workflow_events`` history (read back from a real temp SQLite
backend via ``EventRouter.history``) contains exactly one corresponding event
per transition, in the same order, each attributed to the run.

**Validates: Requirements 4.1**
"""

from __future__ import annotations

import uuid
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.database import SQLiteBackend
from core.event_router import EventRouter, WorkflowEventType

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Step states a Workflow_Step can move between (mirrors the workflow_steps
# state vocabulary in the design's data model).
_STEP_STATES = (
    "pending",
    "ready",
    "running",
    "awaiting_approval",
    "completed",
    "failed",
    "cancelled",
    "skipped",
)


@st.composite
def step_transitions(draw: st.DrawFn) -> list[dict]:
    """Generate a non-empty ordered sequence of step state transitions.

    Each transition records the step it applies to and the state moved into.
    A small pool of step ids is reused so the sequence interleaves transitions
    across several steps, the way a real run does.
    """
    step_ids = draw(
        st.lists(st.text(min_size=1, max_size=8), min_size=1, max_size=5, unique=True)
    )
    transition = st.fixed_dictionaries(
        {
            "step_id": st.sampled_from(step_ids),
            "to_state": st.sampled_from(_STEP_STATES),
        }
    )
    return draw(st.lists(transition, min_size=1, max_size=40))


# ---------------------------------------------------------------------------
# Property 10: Every step transition emits a corresponding event
# ---------------------------------------------------------------------------


# deadline=None: each example does real (temp) SQLite I/O whose timing varies;
# the property is about event/transition correspondence, not latency.
@settings(
    max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow]
)
@given(transitions=step_transitions())
def test_every_step_transition_emits_one_event(
    transitions: list[dict], tmp_path_factory
) -> None:
    """Emitting one event per step transition yields exactly one persisted,
    run-attributed STEP_STATE_CHANGED event per transition, in order."""
    # Fresh, isolated temp SQLite backend per example (in-memory-equivalent on
    # disk; SQLite connects per-operation so a unique file is used each time).
    db_dir: Path = tmp_path_factory.mktemp("per-transition-events")
    backend = SQLiteBackend(db_dir / f"events-{uuid.uuid4().hex}.db")
    router = EventRouter(backend)
    run_id = f"run-{uuid.uuid4().hex}"

    for index, transition in enumerate(transitions):
        router.emit(
            run_id,
            WorkflowEventType.STEP_STATE_CHANGED,
            f"step {transition['step_id']} -> {transition['to_state']}",
            step_id=transition["step_id"],
            payload={"to": transition["to_state"], "index": index},
        )

    # Read back the *persisted* history (proves events were stored, not just
    # returned) and keep only step-transition events.
    history = [
        event
        for event in router.history(run_id)
        if event.type == WorkflowEventType.STEP_STATE_CHANGED
    ]

    # Exactly one event per transition.
    assert len(history) == len(transitions)

    # Each event is attributed to the run, carries a monotonic per-run seq, and
    # corresponds one-to-one (in order) with its transition.
    for seq_index, (event, transition) in enumerate(
        zip(history, transitions), start=1
    ):
        assert event.run_id == run_id
        assert event.seq == seq_index
        assert event.step_id == transition["step_id"]
        assert event.payload["to"] == transition["to_state"]
        assert event.payload["index"] == seq_index - 1
