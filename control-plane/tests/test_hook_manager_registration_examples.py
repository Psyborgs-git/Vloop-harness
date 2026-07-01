"""Example-based unit tests for Hook_Manager registration (`core/hook_manager.py`).

Covers task 27.3 with concrete examples of Requirement 17.1: the Hook_Manager
allows Event_Hooks to be registered against *defined* lifecycle events of a
Workflow_Run.

* Req 17.1 - a hook registered against a defined :class:`LifecycleEvent` is
  retrievable via :meth:`HookManager.hooks_for`, multiple hooks bind to the same
  event and are returned in registration order, distinct events keep separate
  registries, and registering against an undefined/unknown lifecycle event
  raises ``ValueError``.
* A guardrail is necessarily blocking, so constructing/registering one forces
  ``blocking=True`` regardless of how it was configured.

**Validates: Requirements 17.1**
"""

from __future__ import annotations

import pytest

from core.hook_manager import (
    EventHook,
    HookContext,
    HookManager,
    LifecycleEvent,
)


def _noop(_ctx: HookContext) -> None:
    """A trivial hook action used wherever behavior is irrelevant to registration."""
    return None


# ---------------------------------------------------------------------------
# Req 17.1: hooks register against defined lifecycle events and are retrievable
# ---------------------------------------------------------------------------


def test_registered_hook_is_retrievable_for_its_event():
    """A hook registered for a defined event is returned by hooks_for."""
    manager = HookManager()

    hook = manager.register_hook(
        name="notify",
        event=LifecycleEvent.RUN_COMPLETED,
        action=_noop,
    )

    registered = manager.hooks_for(LifecycleEvent.RUN_COMPLETED)
    assert registered == [hook]
    assert registered[0].name == "notify"
    assert registered[0].event == LifecycleEvent.RUN_COMPLETED.value


def test_register_accepts_a_prebuilt_event_hook():
    """register() binds a prebuilt EventHook to its defined lifecycle event."""
    manager = HookManager()
    hook = EventHook(
        name="log-start",
        event=LifecycleEvent.RUN_STARTED,
        action=_noop,
    )

    returned = manager.register(hook)

    assert returned is hook
    assert manager.hooks_for(LifecycleEvent.RUN_STARTED) == [hook]


def test_event_may_be_supplied_as_a_string_value():
    """A defined lifecycle event passed as its string value registers and resolves."""
    manager = HookManager()

    manager.register_hook(name="on-step", event="step.completed", action=_noop)

    # Retrievable by both the string value and the enum member.
    by_string = manager.hooks_for("step.completed")
    by_enum = manager.hooks_for(LifecycleEvent.STEP_COMPLETED)
    assert len(by_string) == 1
    assert by_string == by_enum
    assert by_string[0].event == "step.completed"


# ---------------------------------------------------------------------------
# Req 17.1: multiple hooks per event, preserved in registration order
# ---------------------------------------------------------------------------


def test_multiple_hooks_for_one_event_kept_in_registration_order():
    """Several hooks on the same event are returned in the order registered."""
    manager = HookManager()

    first = manager.register_hook(name="first", event=LifecycleEvent.STEP_STARTED, action=_noop)
    second = manager.register_hook(name="second", event=LifecycleEvent.STEP_STARTED, action=_noop)
    third = manager.register_hook(name="third", event=LifecycleEvent.STEP_STARTED, action=_noop)

    registered = manager.hooks_for(LifecycleEvent.STEP_STARTED)
    assert registered == [first, second, third]
    assert [h.name for h in registered] == ["first", "second", "third"]


def test_hooks_for_different_events_are_isolated():
    """Hooks registered for distinct events do not leak across event registries."""
    manager = HookManager()

    started = manager.register_hook(name="on-start", event=LifecycleEvent.RUN_STARTED, action=_noop)
    failed = manager.register_hook(name="on-fail", event=LifecycleEvent.RUN_FAILED, action=_noop)

    assert manager.hooks_for(LifecycleEvent.RUN_STARTED) == [started]
    assert manager.hooks_for(LifecycleEvent.RUN_FAILED) == [failed]


def test_hooks_for_unregistered_event_is_empty():
    """An event with no registered hooks returns an empty list, not an error."""
    manager = HookManager()

    assert manager.hooks_for(LifecycleEvent.TOOL_INVOKED) == []


def test_hooks_for_returns_a_copy_that_does_not_mutate_the_registry():
    """The returned list is a snapshot; mutating it leaves the registry intact."""
    manager = HookManager()
    manager.register_hook(name="only", event=LifecycleEvent.RUN_CREATED, action=_noop)

    snapshot = manager.hooks_for(LifecycleEvent.RUN_CREATED)
    snapshot.clear()

    assert len(manager.hooks_for(LifecycleEvent.RUN_CREATED)) == 1


# ---------------------------------------------------------------------------
# Req 17.1: registering against an undefined/unknown lifecycle event raises
# ---------------------------------------------------------------------------


def test_register_hook_against_unknown_event_raises():
    """Binding a hook to an event outside LifecycleEvent is rejected."""
    manager = HookManager()

    with pytest.raises(ValueError, match="not a defined lifecycle event"):
        manager.register_hook(name="bad", event="run.exploded", action=_noop)


def test_constructing_event_hook_with_unknown_event_raises():
    """An EventHook itself rejects an undefined lifecycle event at construction."""
    with pytest.raises(ValueError, match="not a defined lifecycle event"):
        EventHook(name="bad", event="not.an.event", action=_noop)


def test_hooks_for_unknown_event_raises():
    """Looking up hooks for an undefined event is a programming error."""
    manager = HookManager()

    with pytest.raises(ValueError, match="not a defined lifecycle event"):
        manager.hooks_for("definitely.not.defined")


def test_unknown_event_registration_does_not_corrupt_registry():
    """A rejected registration leaves previously registered hooks untouched."""
    manager = HookManager()
    good = manager.register_hook(name="good", event=LifecycleEvent.RUN_STARTED, action=_noop)

    with pytest.raises(ValueError):
        manager.register_hook(name="bad", event="bogus.event", action=_noop)

    assert manager.hooks_for(LifecycleEvent.RUN_STARTED) == [good]


# ---------------------------------------------------------------------------
# Req 17.1 / 17.4: a guardrail is forced blocking on registration
# ---------------------------------------------------------------------------


def test_guardrail_registration_is_forced_blocking():
    """A guardrail registered as non-blocking is coerced to blocking."""
    manager = HookManager()

    hook = manager.register_hook(
        name="guard",
        event=LifecycleEvent.STEP_STARTED,
        action=_noop,
        guardrail=True,
        blocking=False,
    )

    assert hook.guardrail is True
    assert hook.blocking is True
    assert manager.hooks_for(LifecycleEvent.STEP_STARTED) == [hook]


def test_guardrail_event_hook_forces_blocking_at_construction():
    """Constructing a guardrail EventHook forces blocking regardless of input."""
    hook = EventHook(
        name="guard",
        event=LifecycleEvent.TOOL_INVOKED,
        action=_noop,
        guardrail=True,
        blocking=False,
    )

    assert hook.guardrail is True
    assert hook.blocking is True


def test_non_guardrail_blocking_flag_is_respected():
    """A plain (non-guardrail) hook keeps whatever blocking flag it was given."""
    manager = HookManager()

    blocking = manager.register_hook(
        name="blocking-plain",
        event=LifecycleEvent.STEP_COMPLETED,
        action=_noop,
        blocking=True,
    )
    non_blocking = manager.register_hook(
        name="async-plain",
        event=LifecycleEvent.STEP_COMPLETED,
        action=_noop,
        blocking=False,
    )

    assert blocking.blocking is True
    assert blocking.guardrail is False
    assert non_blocking.blocking is False
    assert non_blocking.guardrail is False


def test_event_hook_requires_a_callable_action():
    """An EventHook with a non-callable action is rejected at construction."""
    with pytest.raises(ValueError, match="requires a callable action"):
        EventHook(name="no-action", event=LifecycleEvent.RUN_STARTED, action=None)  # type: ignore[arg-type]
