"""Property-based test for event run attribution.

# Feature: orchestration-engine-completion, Property 46: Every orchestration event is attributable to a run

Property 46 states that *for any* event recorded by an orchestration subsystem,
the event includes the associated Workflow_Run identifier (Requirement 21.5).

For the Event_Router this means:

* Every successfully emitted and persisted ``WorkflowEvent`` carries a
  non-empty ``run_id`` equal to the run it was emitted for, both in the returned
  object and in the ``workflow_events`` row.
* Emitting with an empty ``run_id`` raises ``ValueError`` and persists no orphan
  event (there is no run to attribute it to).
* A Kernel event that cannot be attributed to a run (no ``run_id`` argument and
  no run association in its attributes) is dropped — ``normalize_kernel_event``
  returns ``None`` and nothing is persisted.

**Validates: Requirements 21.5**
"""

from __future__ import annotations

from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.database import SQLiteBackend
from core.event_router import EventRouter, WorkflowEventType

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Non-empty run ids: any text that is truthy (the Event_Router treats any
# non-empty string as a valid run association).
_run_ids = st.text(min_size=1, max_size=40).filter(lambda s: bool(s))

_event_types = st.sampled_from(
    [
        WorkflowEventType.RUN_CREATED,
        WorkflowEventType.RUN_COMPLETED,
        WorkflowEventType.RUN_FAILED,
        WorkflowEventType.STEP_STATE_CHANGED,
        WorkflowEventType.APPROVAL_REQUIRED,
        WorkflowEventType.BUDGET_STATUS,
        WorkflowEventType.KERNEL_EVENT,
    ]
)

_messages = st.text(max_size=60)
_step_ids = st.one_of(st.none(), st.text(min_size=1, max_size=20))

# JSON-safe payload values so persistence (to_json) never fails.
_payload_scalars = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(10**9), max_value=10**9),
    st.text(max_size=20),
)
_payloads = st.one_of(
    st.none(),
    st.dictionaries(st.text(max_size=10), _payload_scalars, max_size=5),
)

# Empty / falsy run ids that must be rejected by emit().
_empty_run_ids = st.sampled_from(["", None])


def _fresh_router(tmp_path: Path, name: str) -> tuple[EventRouter, SQLiteBackend]:
    backend = SQLiteBackend(tmp_path / name)
    return EventRouter(backend), backend


# ---------------------------------------------------------------------------
# Property 46: every emitted/persisted event is attributable to its run
# ---------------------------------------------------------------------------


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    run_id=_run_ids,
    event_type=_event_types,
    message=_messages,
    step_id=_step_ids,
    payload=_payloads,
)
def test_emitted_event_is_attributable_to_run(
    run_id: str,
    event_type: str,
    message: str,
    step_id: str | None,
    payload: dict | None,
    tmp_path_factory,
) -> None:
    """Any successfully emitted event carries the run_id it was emitted for."""
    base = tmp_path_factory.mktemp("attribution")
    router, backend = _fresh_router(base, "emit.db")

    event = router.emit(
        run_id,
        event_type,
        message,
        step_id=step_id,
        payload=payload,
    )

    # The returned event is attributed to the run it was emitted for.
    assert event.run_id == run_id
    assert event.run_id  # non-empty

    # The persisted row carries the same non-empty run_id.
    row = backend.fetch_one(
        "SELECT run_id FROM workflow_events WHERE run_id = ? AND seq = ?",
        (run_id, event.seq),
    )
    assert row is not None
    assert row["run_id"] == run_id
    assert row["run_id"]  # non-empty

    # Every event in this run's history is attributed to the run.
    for persisted in router.history(run_id):
        assert persisted.run_id == run_id


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    empty_run_id=_empty_run_ids,
    event_type=_event_types,
    message=_messages,
    payload=_payloads,
)
def test_empty_run_id_raises_and_persists_no_orphan(
    empty_run_id,
    event_type: str,
    message: str,
    payload: dict | None,
    tmp_path_factory,
) -> None:
    """Emitting with an empty run_id raises and leaves no orphan event."""
    base = tmp_path_factory.mktemp("orphan")
    router, backend = _fresh_router(base, "orphan.db")

    try:
        router.emit(empty_run_id, event_type, message, payload=payload)
        raised = False
    except ValueError:
        raised = True

    assert raised, "emit() must reject an empty/missing run_id"

    # No orphan event of any kind was persisted.
    row = backend.fetch_one("SELECT COUNT(*) AS n FROM workflow_events", ())
    assert int(row["n"]) == 0


class _FakeKernelEvent:
    """Minimal duck-typed Kernel event record for normalization tests."""

    def __init__(self, event_type: str, attributes: dict) -> None:
        self.event_type = event_type
        self.resource_type = ""
        self.resource_id = ""
        self.status = ""
        self.message = ""
        self.attributes = attributes


# Attribute dicts that carry NO run association.
_unattributed_attributes = st.dictionaries(
    st.text(max_size=10).filter(lambda k: k not in ("run_id", "workflow_run_id")),
    st.text(max_size=20),
    max_size=5,
)


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    event_type=st.text(max_size=30),
    attributes=_unattributed_attributes,
)
def test_unattributed_kernel_event_is_dropped(
    event_type: str,
    attributes: dict,
    tmp_path_factory,
) -> None:
    """A Kernel event with no run association is dropped and not persisted."""
    base = tmp_path_factory.mktemp("dropped")
    router, backend = _fresh_router(base, "dropped.db")

    record = _FakeKernelEvent(event_type, attributes)
    result = router.normalize_kernel_event(record)

    # No run to attribute to -> not a workflow event.
    assert result is None

    # Nothing was persisted for an unattributable event.
    row = backend.fetch_one("SELECT COUNT(*) AS n FROM workflow_events", ())
    assert int(row["n"]) == 0


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    run_id=_run_ids,
    event_type=st.text(max_size=30),
    attributes=_unattributed_attributes,
)
def test_kernel_event_attributed_when_run_resolvable(
    run_id: str,
    event_type: str,
    attributes: dict,
    tmp_path_factory,
) -> None:
    """A Kernel event with a resolvable run is attributed to that run."""
    base = tmp_path_factory.mktemp("attributed")
    router, _ = _fresh_router(base, "attributed.db")

    # Run association supplied either explicitly or via attributes.
    record = _FakeKernelEvent(event_type, dict(attributes))
    event = router.normalize_kernel_event(record, run_id=run_id)

    assert event is not None
    assert event.run_id == run_id
    assert event.run_id  # non-empty
