"""Hook_Manager — lifecycle Event_Hooks with failure isolation and guardrails.

The Hook_Manager is the Control_Plane subsystem that runs configured
:class:`EventHook` actions at defined lifecycle points of a Workflow_Run
(Requirement 17.1). It owns four guarantees the design requires:

* **Registration against defined lifecycle events (Req 17.1).** Hooks are
  registered against a fixed vocabulary of run/step lifecycle events
  (:class:`LifecycleEvent`); registering against an unknown event is a
  programming error and is rejected.
* **Run with event context; non-blocking hooks do not block (Req 17.2).** When a
  lifecycle event fires, every hook registered for it runs with the event's
  :class:`HookContext`. A *non-blocking* hook is dispatched fire-and-forget on a
  background thread, so the run continues without waiting for it to finish.
* **Failure isolation (Req 17.3).** If a hook raises or fails, the error is
  recorded in the run's event history (via the :class:`~core.event_router.EventRouter`)
  and the run continues — *unless* the hook is a blocking guardrail, which fails
  closed (see below).
* **Blocking guardrails (Req 17.4).** A *blocking guardrail* is awaited and
  returns an allow/deny decision. When it denies (or errors, failing closed) the
  associated Workflow_Step is stopped from proceeding: :meth:`HookManager.trigger`
  returns a result whose :attr:`HookExecutionResult.allowed` is ``False`` so the
  caller (the DAG_Executor / step runner) does not proceed.

The Hook_Manager owns registration, dispatch, isolation, and the guardrail
verdict; the *action* a hook performs (a webhook call, a log entry, a guardrail
check) is supplied as an injectable callable. This keeps the manager free of any
transport dependency and makes its behavior deterministic for tests.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.event_router import EventRouter

LOGGER = logging.getLogger("vloop.control_plane.hook_manager")


class LifecycleEvent(str, Enum):
    """The defined lifecycle events a Workflow_Run exposes for hooks (Req 17.1).

    Hooks may only be registered against one of these events. Values are the
    same stable, user-facing vocabulary the rest of the orchestrator uses.
    """

    RUN_CREATED = "run.created"
    RUN_STARTED = "run.started"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    RUN_CANCELLED = "run.cancelled"
    STEP_READY = "step.ready"
    STEP_STARTED = "step.started"
    STEP_COMPLETED = "step.completed"
    STEP_FAILED = "step.failed"
    TOOL_INVOKED = "tool.invoked"


# Set of valid lifecycle event values, used to validate registration.
_DEFINED_EVENTS: frozenset[str] = frozenset(event.value for event in LifecycleEvent)

# Event types recorded in the run event history for hook outcomes (Req 17.3, 17.4).
HOOK_ERROR_EVENT = "hook.error"
HOOK_DENIED_EVENT = "hook.denied"


# A hook action receives the event context and performs its side effect. For a
# guardrail it returns an allow/deny verdict (see :func:`_coerce_decision`); for
# a plain hook the return value is ignored.
HookCallable = Callable[["HookContext"], Any]


@dataclass(slots=True)
class HookContext:
    """The event context a hook action runs with (Req 17.2).

    Carries the lifecycle ``event`` that fired, the ``run_id`` the event is
    attributed to (so errors can be recorded against the run's history), the
    optional ``step_id`` a guardrail can stop, and an arbitrary ``data`` payload
    describing the event.
    """

    event: str
    run_id: str
    step_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class GuardrailDecision:
    """A blocking guardrail's verdict on whether the action may proceed.

    ``allow`` is ``True`` to permit the associated step to proceed, ``False`` to
    deny it (Req 17.4). ``reason`` is a short, user-facing explanation recorded
    when the guardrail denies.
    """

    allow: bool
    reason: str = ""

    @classmethod
    def allowed(cls, reason: str = "") -> "GuardrailDecision":
        return cls(True, reason)

    @classmethod
    def denied(cls, reason: str = "") -> "GuardrailDecision":
        return cls(False, reason)


@dataclass(slots=True)
class EventHook:
    """A user- or template-configured action bound to a lifecycle event.

    ``action`` is the callable run with the :class:`HookContext`. ``blocking``
    marks a hook the run waits for; a non-blocking hook is dispatched
    fire-and-forget (Req 17.2). ``guardrail`` marks a hook whose allow/deny
    verdict can stop the associated step (Req 17.4); a guardrail is necessarily
    blocking, so constructing one forces ``blocking`` to ``True``.
    """

    name: str
    event: str
    action: HookCallable
    blocking: bool = False
    guardrail: bool = False

    def __post_init__(self) -> None:
        if self.action is None or not callable(self.action):
            raise ValueError(f"hook '{self.name}' requires a callable action")
        self.event = _normalize_event(self.event)
        # A guardrail's verdict must be known before the step proceeds, so a
        # guardrail is always blocking regardless of how it was configured.
        if self.guardrail:
            self.blocking = True


@dataclass(slots=True)
class HookExecutionResult:
    """The outcome of triggering every hook registered for one lifecycle event.

    ``allowed`` is the verdict the caller acts on: ``True`` means the associated
    Workflow_Step may proceed, ``False`` means a blocking guardrail denied it and
    the step must not proceed (Req 17.4). ``ran`` lists blocking hooks executed
    synchronously; ``dispatched`` lists non-blocking hooks fired without waiting
    (Req 17.2); ``errors`` records hook failures that were isolated (Req 17.3).
    """

    event: str
    run_id: str
    step_id: str | None = None
    allowed: bool = True
    denied_by: str | None = None
    deny_reason: str | None = None
    ran: list[str] = field(default_factory=list)
    dispatched: list[str] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)

    @property
    def should_proceed(self) -> bool:
        """``True`` when no blocking guardrail denied the action (Req 17.4)."""
        return self.allowed


class HookManager:
    """Registers and runs lifecycle Event_Hooks with isolation and guardrails."""

    def __init__(self, event_router: EventRouter | None = None) -> None:
        # The Event_Router is where hook errors and denials are recorded in the
        # run's event history (Req 17.3, 17.4). It is optional so the manager can
        # be exercised standalone; when absent, outcomes are logged instead.
        self._event_router = event_router
        self._lock = threading.RLock()
        self._hooks: dict[str, list[EventHook]] = {}
        # Background threads for non-blocking hooks; tracked only so a graceful
        # shutdown (or a test) can wait for them. The run itself never waits.
        self._async_threads: list[threading.Thread] = []

    # -- registration -------------------------------------------------------

    def register(self, hook: EventHook) -> EventHook:
        """Register an :class:`EventHook` against its lifecycle event (Req 17.1).

        Registering against an event outside :class:`LifecycleEvent` raises
        ``ValueError`` — hooks bind only to *defined* lifecycle events.
        """
        event = _normalize_event(hook.event)
        with self._lock:
            self._hooks.setdefault(event, []).append(hook)
        return hook

    def register_hook(
        self,
        *,
        name: str,
        event: LifecycleEvent | str,
        action: HookCallable,
        blocking: bool = False,
        guardrail: bool = False,
    ) -> EventHook:
        """Build and register an :class:`EventHook` in one call (Req 17.1)."""
        hook = EventHook(
            name=name,
            event=_normalize_event(event),
            action=action,
            blocking=blocking,
            guardrail=guardrail,
        )
        return self.register(hook)

    def hooks_for(self, event: LifecycleEvent | str) -> list[EventHook]:
        """Return the hooks registered for ``event``, in registration order."""
        with self._lock:
            return list(self._hooks.get(_normalize_event(event), ()))

    # -- triggering ---------------------------------------------------------

    def trigger(
        self,
        event: LifecycleEvent | str,
        *,
        run_id: str,
        step_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> HookExecutionResult:
        """Run every hook registered for ``event`` with the event context.

        Blocking hooks run synchronously in registration order; non-blocking
        hooks are dispatched fire-and-forget so the run continues without waiting
        (Req 17.2). A hook error is recorded and isolated so the run continues,
        unless the failing hook is a blocking guardrail, which fails closed
        (Req 17.3). When a blocking guardrail denies (or fails closed), evaluation
        stops and the returned result's :attr:`HookExecutionResult.allowed` is
        ``False`` so the associated step does not proceed (Req 17.4).
        """
        normalized = _normalize_event(event)
        context = HookContext(
            event=normalized,
            run_id=run_id,
            step_id=step_id,
            data=dict(data or {}),
        )
        result = HookExecutionResult(
            event=normalized, run_id=run_id, step_id=step_id
        )

        for hook in self.hooks_for(normalized):
            if not hook.blocking:
                # Non-blocking: dispatch and move on without waiting (Req 17.2).
                self._dispatch_async(hook, context)
                result.dispatched.append(hook.name)
                continue

            # Blocking hook: the run waits for it to finish.
            result.ran.append(hook.name)
            try:
                outcome = hook.action(context)
            except Exception as exc:  # noqa: BLE001 - isolate per Req 17.3
                message = str(exc)
                self._record_error(context, hook, message)
                result.errors.append({"hook": hook.name, "error": message})
                if hook.guardrail:
                    # A guardrail that cannot render a verdict fails closed: the
                    # step must not proceed (Req 17.3 exception, Req 17.4).
                    reason = f"guardrail '{hook.name}' failed to evaluate: {message}"
                    self._deny(result, context, hook, reason)
                    break
                # A non-guardrail hook error is isolated; the run continues.
                continue

            if hook.guardrail:
                decision = _coerce_decision(outcome)
                if not decision.allow:
                    reason = decision.reason or f"denied by guardrail '{hook.name}'"
                    self._deny(result, context, hook, reason)
                    break

        return result

    # -- async lifecycle ----------------------------------------------------

    def wait_for_pending(self, timeout: float | None = None) -> None:
        """Wait for dispatched non-blocking hooks to finish.

        Provided for graceful shutdown and deterministic testing only. The run
        path never calls this — non-blocking hooks must not block the run
        (Req 17.2).
        """
        with self._lock:
            threads = list(self._async_threads)
        for thread in threads:
            thread.join(timeout)
        with self._lock:
            self._async_threads = [t for t in self._async_threads if t.is_alive()]

    # -- internals ----------------------------------------------------------

    def _dispatch_async(self, hook: EventHook, context: HookContext) -> None:
        """Run a non-blocking hook on a background thread (Req 17.2).

        The run does not wait on this thread. Any error the hook raises is still
        recorded in the run's event history (Req 17.3), just asynchronously.
        """

        def _run() -> None:
            try:
                hook.action(context)
            except Exception as exc:  # noqa: BLE001 - isolate per Req 17.3
                self._record_error(context, hook, str(exc))

        thread = threading.Thread(
            target=_run,
            name=f"hook-{hook.name}",
            daemon=True,
        )
        with self._lock:
            # Prune finished threads so the list does not grow unbounded.
            self._async_threads = [t for t in self._async_threads if t.is_alive()]
            self._async_threads.append(thread)
        thread.start()

    def _deny(
        self,
        result: HookExecutionResult,
        context: HookContext,
        hook: EventHook,
        reason: str,
    ) -> None:
        """Mark the result denied by a blocking guardrail and record it (Req 17.4)."""
        result.allowed = False
        result.denied_by = hook.name
        result.deny_reason = reason
        self._record_denied(context, hook, reason)

    def _record_error(self, context: HookContext, hook: EventHook, message: str) -> None:
        """Record a hook error in the run event history (Req 17.3)."""
        payload = {
            "hook": hook.name,
            "event": context.event,
            "guardrail": hook.guardrail,
            "blocking": hook.blocking,
            "error": message,
        }
        if self._event_router is not None and context.run_id:
            try:
                self._event_router.emit(
                    context.run_id,
                    HOOK_ERROR_EVENT,
                    f"event hook '{hook.name}' failed: {message}",
                    step_id=context.step_id,
                    payload=payload,
                )
                return
            except Exception:  # noqa: BLE001 - never let recording break the run
                LOGGER.exception("failed to record hook error in event history")
        LOGGER.error("event hook '%s' failed: %s", hook.name, message)

    def _record_denied(self, context: HookContext, hook: EventHook, reason: str) -> None:
        """Record a guardrail denial in the run event history (Req 17.4)."""
        payload = {
            "hook": hook.name,
            "event": context.event,
            "step_id": context.step_id,
            "reason": reason,
        }
        if self._event_router is not None and context.run_id:
            try:
                self._event_router.emit(
                    context.run_id,
                    HOOK_DENIED_EVENT,
                    f"guardrail '{hook.name}' denied the action: {reason}",
                    step_id=context.step_id,
                    payload=payload,
                )
                return
            except Exception:  # noqa: BLE001 - never let recording break the run
                LOGGER.exception("failed to record guardrail denial in event history")
        LOGGER.warning("guardrail '%s' denied the action: %s", hook.name, reason)


def _normalize_event(event: LifecycleEvent | str) -> str:
    """Coerce ``event`` to a defined lifecycle event value or raise.

    Hooks bind only to defined lifecycle events (Req 17.1); an unknown event is
    a programming error.
    """
    value = event.value if isinstance(event, LifecycleEvent) else str(event)
    if value not in _DEFINED_EVENTS:
        raise ValueError(
            f"'{value}' is not a defined lifecycle event; "
            f"expected one of {sorted(_DEFINED_EVENTS)}"
        )
    return value


def _coerce_decision(outcome: Any) -> GuardrailDecision:
    """Interpret a guardrail action's return value as a :class:`GuardrailDecision`.

    Accepts a :class:`GuardrailDecision` directly; a ``bool`` (``True`` allow /
    ``False`` deny); ``None`` (no objection → allow); or a mapping carrying an
    ``allow``/``allowed`` flag and optional ``reason``. Any other truthy value is
    treated as an allow so a hook that merely returns a result object does not
    accidentally block a step.
    """
    if isinstance(outcome, GuardrailDecision):
        return outcome
    if outcome is None:
        return GuardrailDecision.allowed()
    if isinstance(outcome, bool):
        return GuardrailDecision(allow=outcome)
    if isinstance(outcome, dict):
        if "allow" in outcome:
            allow = bool(outcome["allow"])
        elif "allowed" in outcome:
            allow = bool(outcome["allowed"])
        else:
            allow = True
        return GuardrailDecision(allow=allow, reason=str(outcome.get("reason", "")))
    return GuardrailDecision.allowed()
