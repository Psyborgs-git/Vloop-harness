"""Subagent_Manager — bounded, isolated child-agent delegation.

Provides :class:`SubagentManager`, the Control_Plane subsystem a running agent
uses to delegate work to *subagents* (child agents). The manager enforces the
four guarantees the design requires for delegation:

* **Isolated context (Req 15.1).** Each subagent runs against a deep copy of the
  parent's context. Mutations a subagent makes to its own context never leak
  back to the parent, so a misbehaving or exploratory child cannot corrupt the
  parent's state.
* **Toolset restriction (Req 15.2).** A subagent is restricted to exactly the
  toolset granted at spawn time. The isolated :class:`SubagentContext` advertises
  only those toolsets and offers no path to any other, so the granted set is the
  child's whole world of tools.
* **Concurrency bound with queuing (Req 15.3).** At most ``concurrency_limit``
  subagents run at once. Spawn requests beyond the limit block (queue) until an
  active subagent completes and frees a slot. The bound is enforced by a
  :class:`threading.BoundedSemaphore`, which makes the queueing deterministic and
  testable.
* **Result return + usage accounting (Req 15.4).** On completion the subagent's
  result is returned to the parent (caller) and its token usage is recorded
  against the enclosing Workflow_Run — both in an in-memory ledger and, when a
  :class:`~core.database.DatabaseBackend` is supplied, persisted onto the run's
  ``budget_json`` so accounting survives a restart.

The actual subagent execution is supplied as an injectable *runner* callable
(:data:`SubagentRunner`). The manager owns isolation, the concurrency bound, and
accounting; the runner owns "what a subagent does". This keeps the manager free
of any real agent/model dependency and makes its behavior fully deterministic
for tests.
"""

from __future__ import annotations

import copy
import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from core.database import DatabaseBackend
from core.helpers import from_json, to_json
from core.orchestration_types import Budget

# A runner receives the isolated, toolset-restricted context for one subagent
# and returns that subagent's outcome. It is the only thing the manager does not
# own, so tests can supply a deterministic stand-in for a real agent.
SubagentRunner = Callable[["SubagentContext"], "SubagentResult"]


@dataclass(slots=True, frozen=True)
class SubagentSpec:
    """A request to spawn one subagent under a parent Workflow_Run.

    ``run_id`` attributes the subagent (and its usage) to the enclosing run.
    ``toolset`` is the set of toolset names granted to the child at spawn time —
    the child is restricted to exactly this set (Req 15.2). ``context`` is the
    parent's context; the manager deep-copies it so the child's view is isolated
    (Req 15.1) and the original is never mutated.
    """

    run_id: str
    task: str = ""
    toolset: Sequence[str] = ()
    context: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SubagentContext:
    """The isolated, toolset-restricted world handed to a subagent runner.

    ``context`` is a private deep copy of the parent's context; mutating it has
    no effect on the parent (Req 15.1). ``toolset`` is the immutable set of
    toolsets granted at spawn; :meth:`allows` is the only sanctioned way to ask
    whether a tool/toolset is in scope, and there is no path to anything outside
    it (Req 15.2).
    """

    run_id: str
    task: str
    toolset: frozenset[str]
    context: dict[str, Any]

    def allows(self, toolset: str) -> bool:
        """Return ``True`` only if ``toolset`` was granted to this subagent."""
        return toolset in self.toolset


@dataclass(slots=True)
class SubagentResult:
    """The outcome of a subagent, returned to the parent on completion.

    ``token_usage`` is recorded against the run by the manager (Req 15.4).
    ``toolset`` echoes the granted scope so the parent can audit what the child
    was permitted to use.
    """

    run_id: str
    output: Any = None
    token_usage: int = 0
    ok: bool = True
    error_message: str | None = None
    toolset: frozenset[str] = field(default_factory=frozenset)


class SubagentManager:
    """Spawns isolated, toolset-restricted subagents under a concurrency bound."""

    def __init__(
        self,
        runner: SubagentRunner,
        *,
        concurrency_limit: int = 1,
        state: DatabaseBackend | None = None,
    ) -> None:
        if runner is None:
            raise ValueError("a subagent runner is required")
        self._runner = runner
        self._concurrency_limit = max(1, int(concurrency_limit))
        self._state = state

        # Bounds active subagents and queues excess spawns until a slot frees
        # (Req 15.3). A BoundedSemaphore makes the queueing deterministic.
        self._slots = threading.BoundedSemaphore(self._concurrency_limit)

        # Guards the active/peak counters and the in-memory usage ledger so
        # concurrent spawns cannot race on accounting.
        self._lock = threading.Lock()
        self._active = 0
        self._peak_active = 0
        self._usage_by_run: dict[str, int] = {}

    # -- introspection ------------------------------------------------------

    @property
    def concurrency_limit(self) -> int:
        """The maximum number of subagents permitted to run concurrently."""
        return self._concurrency_limit

    @property
    def active_count(self) -> int:
        """The number of subagents currently executing."""
        with self._lock:
            return self._active

    @property
    def peak_active(self) -> int:
        """The greatest number of subagents observed running at once.

        Always ``<= concurrency_limit`` (Req 15.3); useful for asserting the
        bound held across a batch of spawns.
        """
        with self._lock:
            return self._peak_active

    def usage_for(self, run_id: str) -> int:
        """Total subagent token usage recorded against ``run_id`` (Req 15.4)."""
        with self._lock:
            return self._usage_by_run.get(run_id, 0)

    # -- spawning -----------------------------------------------------------

    def spawn(self, spec: SubagentSpec) -> SubagentResult:
        """Spawn one subagent, blocking (queuing) if at the concurrency bound.

        The child receives an isolated context and is restricted to the toolset
        granted in ``spec`` (Req 15.1, 15.2). If all slots are occupied the call
        blocks until an active subagent completes and frees one (Req 15.3). On
        completion the result is returned to the caller and the child's token
        usage is recorded against the run (Req 15.4).
        """
        # Acquire a slot — this is the queue: excess spawns wait here until an
        # active subagent releases its slot.
        self._slots.acquire()
        try:
            with self._lock:
                self._active += 1
                if self._active > self._peak_active:
                    self._peak_active = self._active

            context = self._isolate(spec)
            try:
                result = self._runner(context)
            except Exception as exc:  # noqa: BLE001 - surface as a failed result
                result = SubagentResult(
                    run_id=spec.run_id,
                    output=None,
                    token_usage=0,
                    ok=False,
                    error_message=str(exc),
                    toolset=context.toolset,
                )
        finally:
            with self._lock:
                self._active -= 1
            self._slots.release()

        # Return the result to the parent and record usage against the run.
        self._record_usage(spec.run_id, result.token_usage)
        return result

    def spawn_many(self, specs: Iterable[SubagentSpec]) -> list[SubagentResult]:
        """Spawn several subagents concurrently, bounded by the limit.

        Each spec is run on its own thread; the concurrency bound and queueing
        are enforced by :meth:`spawn` (Req 15.3). Results are returned in the
        same order as ``specs`` regardless of completion order.
        """
        spec_list = list(specs)
        results: list[SubagentResult | None] = [None] * len(spec_list)
        threads: list[threading.Thread] = []

        def _run(index: int, spec: SubagentSpec) -> None:
            results[index] = self.spawn(spec)

        for index, spec in enumerate(spec_list):
            thread = threading.Thread(target=_run, args=(index, spec), daemon=True)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Every slot was filled by the loop above, so no entry remains None.
        return [result for result in results if result is not None]

    # -- internals ----------------------------------------------------------

    def _isolate(self, spec: SubagentSpec) -> SubagentContext:
        """Build the isolated, toolset-restricted context for a subagent.

        The parent context is deep-copied so child mutations cannot leak back
        (Req 15.1); the toolset is frozen to the set granted at spawn (Req 15.2).
        """
        return SubagentContext(
            run_id=spec.run_id,
            task=spec.task,
            toolset=frozenset(spec.toolset),
            context=copy.deepcopy(dict(spec.context)),
        )

    def _record_usage(self, run_id: str, tokens: int) -> None:
        """Record ``tokens`` of subagent usage against ``run_id`` (Req 15.4).

        Always updates the in-memory ledger; when a DatabaseBackend is present
        the run's ``budget_json`` is updated too so accounting survives restart.
        """
        charge = max(0, int(tokens or 0))
        with self._lock:
            self._usage_by_run[run_id] = self._usage_by_run.get(run_id, 0) + charge
        if charge and self._state is not None:
            self._persist_usage(run_id, charge)

    def _persist_usage(self, run_id: str, charge: int) -> None:
        """Add ``charge`` to the run's persisted ``budget_json.used_tokens``."""
        row = self._state.fetch_one(
            "SELECT budget_json FROM workflow_runs WHERE id = ?",
            (run_id,),
        )
        if row is None:
            # No such run to attribute against; the in-memory ledger still holds
            # the usage so it is never silently lost.
            return
        budget_data = from_json(row.get("budget_json"), None) or {}
        budget = Budget(
            max_tokens=budget_data.get("max_tokens"),
            max_cost=budget_data.get("max_cost"),
            used_tokens=int(budget_data.get("used_tokens") or 0) + charge,
            used_cost=float(budget_data.get("used_cost") or 0.0),
        )
        self._state.execute(
            "UPDATE workflow_runs SET budget_json = ? WHERE id = ?",
            (to_json(budget.to_dict()), run_id),
        )
