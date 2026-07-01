"""Property-based test for Hook_Manager execution, isolation, and guardrails.

# Feature: orchestration-engine-completion, Property 40: Event hooks run, isolate failures, and enforce guardrails

Property 40 states that *for any* lifecycle event with a registered Event_Hook:

* **Run with event context; non-blocking hooks do not block (Req 17.2).** Every
  registered hook runs with the event context. A non-blocking hook is dispatched
  fire-and-forget, so the run continues without waiting for it; it still gets
  dispatched (and eventually runs).
* **Failure isolation (Req 17.3).** A hook that raises has its error recorded in
  the run's event history and the run continues — *unless* the failing hook is a
  blocking guardrail, which fails closed.
* **Blocking guardrails (Req 17.4).** When a blocking guardrail denies the action
  (or errors, failing closed), the associated Workflow_Step does not proceed:
  the result's ``allowed`` is ``False`` and evaluation stops at the *first* such
  guardrail.

The test generates random sets of hooks for one lifecycle event — a mix of
non-blocking and blocking plain hooks (succeed or raise) and blocking guardrails
(allow, deny, or error) — registers them, triggers the event against a temp
SQLite-backed :class:`EventRouter`, and asserts the four guarantees above by
comparing the :class:`HookExecutionResult` and the recorded event history to an
independently computed expectation.

**Validates: Requirements 17.2, 17.3, 17.4**
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.database import SQLiteBackend
from core.event_router import EventRouter
from core.hook_manager import (
    HOOK_DENIED_EVENT,
    HOOK_ERROR_EVENT,
    GuardrailDecision,
    HookContext,
    HookManager,
    LifecycleEvent,
)

# ---------------------------------------------------------------------------
# Hook specification model + strategies
# ---------------------------------------------------------------------------

# A single lifecycle event is enough to exercise the property: the registration
# event vocabulary is orthogonal to the run/isolate/guardrail behavior.
_EVENT = LifecycleEvent.STEP_STARTED


@dataclass(frozen=True)
class HookSpec:
    """A declarative description of one hook to register for the event.

    ``kind`` selects the hook's shape and behavior:

    * ``"nb_ok"``    — non-blocking plain hook that succeeds
    * ``"nb_raise"`` — non-blocking plain hook that raises
    * ``"b_ok"``     — blocking plain hook that succeeds
    * ``"b_raise"``  — blocking plain hook that raises
    * ``"g_allow"``  — blocking guardrail that allows
    * ``"g_deny"``   — blocking guardrail that denies
    * ``"g_error"``  — blocking guardrail that raises (must fail closed)
    """

    name: str
    kind: str

    @property
    def blocking(self) -> bool:
        return self.kind != "nb_ok" and self.kind != "nb_raise"

    @property
    def guardrail(self) -> bool:
        return self.kind in ("g_allow", "g_deny", "g_error")

    @property
    def raises(self) -> bool:
        return self.kind in ("nb_raise", "b_raise", "g_error")

    @property
    def stops(self) -> bool:
        """A blocking guardrail that denies or errors stops the step."""
        return self.kind in ("g_deny", "g_error")


_KINDS = ["nb_ok", "nb_raise", "b_ok", "b_raise", "g_allow", "g_deny", "g_error"]


@st.composite
def hook_sets(draw: st.DrawFn) -> list[HookSpec]:
    """Generate a random, registration-ordered set of hook specs for the event."""
    kinds = draw(st.lists(st.sampled_from(_KINDS), min_size=0, max_size=8))
    # Unique, order-revealing names so assertions can identify each hook.
    return [HookSpec(name=f"hook-{i}-{kind}", kind=kind) for i, kind in enumerate(kinds)]


# ---------------------------------------------------------------------------
# Property 40
# ---------------------------------------------------------------------------


@pytest.fixture()
def router(tmp_path: Path) -> EventRouter:
    # A temp SQLite-backed EventRouter: hook errors and denials are recorded in
    # real, queryable run history rather than a mock.
    backend = SQLiteBackend(tmp_path / "hooks-events.db")
    return EventRouter(backend)


# deadline=None: non-blocking hooks run on background threads whose timing
# varies; the property is about behavior, not latency.
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
@given(specs=hook_sets())
def test_hook_execution_isolation_and_guardrails(
    router: EventRouter, specs: list[HookSpec]
) -> None:
    manager = HookManager(event_router=router)

    # Records which hook actions actually executed (by name), so we can confirm
    # non-blocking hooks were genuinely dispatched and ran (Req 17.2).
    executed: set[str] = set()
    executed_lock = threading.Lock()

    def make_action(spec: HookSpec):
        def action(_ctx: HookContext):
            with executed_lock:
                executed.add(spec.name)
            if spec.raises:
                raise RuntimeError(f"boom:{spec.name}")
            if spec.kind == "g_allow":
                return GuardrailDecision.allowed()
            if spec.kind == "g_deny":
                return GuardrailDecision.denied(f"denied:{spec.name}")
            return None

        return action

    for spec in specs:
        manager.register_hook(
            name=spec.name,
            event=_EVENT,
            action=make_action(spec),
            blocking=spec.blocking,
            guardrail=spec.guardrail,
        )

    # --- Independently compute the expectation --------------------------------
    # Evaluation stops at the first blocking guardrail that denies or errors.
    stop_index: int | None = None
    for i, spec in enumerate(specs):
        if spec.stops:
            stop_index = i
            break

    processed = specs if stop_index is None else specs[: stop_index + 1]
    expected_allowed = stop_index is None
    expected_denied_by = None if stop_index is None else specs[stop_index].name

    expected_dispatched = [s.name for s in processed if not s.blocking]
    expected_ran = [s.name for s in processed if s.blocking]
    # result.errors carries only synchronously-handled (blocking) hook errors.
    expected_error_hooks = {
        s.name for s in processed if s.blocking and s.raises
    }

    run_id = f"run-{uuid.uuid4().hex}"

    # --- Trigger --------------------------------------------------------------
    result = manager.trigger(_EVENT, run_id=run_id, step_id="step-1")
    # Let any fire-and-forget non-blocking hooks finish so their side effects and
    # async error recording settle; the run itself never waits on this.
    manager.wait_for_pending(timeout=5.0)

    # --- Req 17.2: non-blocking hooks are dispatched (and eventually run) -----
    assert result.dispatched == expected_dispatched
    for name in expected_dispatched:
        assert name in executed, f"non-blocking hook {name} was never dispatched/run"

    # --- Blocking hooks ran synchronously in registration order ---------------
    assert result.ran == expected_ran
    for name in expected_ran:
        assert name in executed

    # --- Req 17.4: guardrail verdict drives whether the step proceeds ---------
    assert result.allowed is expected_allowed
    assert result.should_proceed is expected_allowed
    assert result.denied_by == expected_denied_by
    if expected_denied_by is not None:
        # Stops at the FIRST denying/erroring guardrail; nothing past it runs.
        assert stop_index is not None
        for later in specs[stop_index + 1 :]:
            assert later.name not in result.dispatched
            assert later.name not in result.ran

    # --- Req 17.3: blocking hook errors are isolated and recorded -------------
    assert {e["hook"] for e in result.errors} == expected_error_hooks

    history = router.history(run_id)
    recorded_error_hooks = {
        evt.payload.get("hook")
        for evt in history
        if evt.type == HOOK_ERROR_EVENT
    }
    # Every blocking error we expected is recorded in the run's event history.
    assert expected_error_hooks <= recorded_error_hooks

    # A non-guardrail hook error never flips the verdict on its own: if the run
    # was denied, some guardrail (not a plain hook) is responsible.
    if not expected_allowed:
        assert specs[stop_index].guardrail  # type: ignore[index]

    # --- Req 17.4: a denial is recorded in the run's event history ------------
    denied_events = [evt for evt in history if evt.type == HOOK_DENIED_EVENT]
    if expected_denied_by is not None:
        assert len(denied_events) == 1
        assert denied_events[0].payload.get("hook") == expected_denied_by
    else:
        assert denied_events == []
