"""Inference_Gateway — the single entry point for all model calls.

The Inference_Gateway centralizes provider selection, retry, fallback, and (in
later tasks) budgets, rate limits, credential pools, and prompt caching for
every model call the Control_Plane makes. It wraps the existing
:class:`~core.provider_service.ProviderService`/``agent_invoker`` rather than
replacing them: this module adds *policy* as a layer over the existing DSPy
invocation path.

This module implements the **call pipeline** (task 15.1):

* **Routing (Req 6.1)** — :meth:`InferenceGateway.call` asks the
  :class:`~core.provider_router.ProviderRouter` for an ordered list of provider
  candidates for the scope's routing policy and current provider health.
* **Bounded inclusive retry (Req 6.2)** — the selected provider is retried with
  exponential backoff *up to and including* the configured maximum retry count.
  For a maximum of ``N`` retries and a provider that returns retryable errors,
  the gateway makes at most ``N + 1`` attempts (one initial attempt plus ``N``
  retries) and never retries more than ``N`` times.
* **Fallback (Req 6.3)** — when a provider is exhausted (its retries are used up
  or it returns a non-retryable error) the gateway advances to the next provider
  in the routing order.
* **Exhaustion (Req 6.4)** — when every candidate provider has failed, the
  gateway records the failure in the Workflow_Run event history (via the
  :class:`~core.event_router.EventRouter`) and raises a
  :class:`ProviderExhaustionError` naming every failed provider.

Budgets and rate limits are layered around the provider-call step (task 16);
credential pools and the prompt cache are added by task 17. The pipeline is
structured so those stages slot in around the provider-call step without
reshaping it: the actual provider invocation is an **injectable callable**
(``provider_call``) that wraps ``ProviderService``, and the backoff sleep is an
**injectable clock** (``sleep``) so tests drive retries without real waiting.

This module also implements **budgets and rate limits** (task 16.1):

* **Budget tracking and blocking (Req 7.1, 7.2)** — :class:`BudgetTracker`
  accumulates tokens/estimated cost per Workflow_Run and blocks the first call
  that would exceed the configured Budget, transitioning the run to the
  ``budget_exceeded`` terminal state.
* **Fail-open (Req 7.3)** — when budget state is unavailable the call proceeds,
  Rate_Limit delays are disabled for it, and the skipped check is recorded.
* **Rate limiting (Req 7.4)** — :class:`RateLimiter` bounds calls per time
  window per provider and delays the excess, driven by an injectable clock.
* **Status events (Req 7.5)** — budget blocks and rate-limit delays emit status
  events through the :class:`~core.event_router.EventRouter`.

Security invariant: this module never reads raw secret values into
Control_Plane state. Provider credentials are obtained through Kernel secret
grants by the injected ``provider_call``; the gateway itself only ever sees a
provider id, a request, and a response.
"""

from __future__ import annotations

import inspect
import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from typing import Any, Callable

from core.database import DatabaseBackend
from core.event_router import EventRouter, WorkflowEventType
from core.helpers import from_json, now_iso, to_json
from core.orchestration_types import (
    Budget,
    GrantContext,
    ModelRequest,
    RoutingPolicy,
    RunScope,
    RunState,
)
from core.provider_router import ProviderHealth, ProviderRouter

LOGGER = logging.getLogger("vloop.control_plane.inference_gateway")

# Event type emitted to the Workflow_Run history when every candidate provider
# has failed (Req 6.4). Kept local to the gateway; the Event_Router accepts any
# event-type string.
INFERENCE_EXHAUSTED_EVENT = "inference.exhausted"


# ---------------------------------------------------------------------------
# Response and error types
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ModelResponse:
    """The result of a successful model call.

    ``provider_id`` records which provider actually served the call after any
    fallback, so callers and the event history can attribute usage correctly.
    ``raw`` carries the underlying provider/LM response object untouched.
    """

    text: str
    provider_id: str
    model: str = ""
    token_usage: int | None = None
    raw: Any = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        # ``raw`` may be an arbitrary, non-serializable provider object; drop it
        # from the dict form used for events/persistence.
        data.pop("raw", None)
        return data


class ProviderCallError(RuntimeError):
    """A model call against a single provider failed.

    ``retryable`` marks whether the gateway should retry the same provider
    (Req 6.2) before advancing to the next one (Req 6.3). Transient/network
    failures are retryable; deterministic failures (bad request, auth rejected)
    are not and should advance the fallback order immediately.
    """

    def __init__(
        self,
        message: str,
        *,
        provider_id: str | None = None,
        retryable: bool = True,
    ) -> None:
        super().__init__(message)
        self.provider_id = provider_id
        self.retryable = retryable


class RetryableProviderError(ProviderCallError):
    """A retryable provider failure (transient error, timeout, 5xx, ...)."""

    def __init__(self, message: str, *, provider_id: str | None = None) -> None:
        super().__init__(message, provider_id=provider_id, retryable=True)


class NonRetryableProviderError(ProviderCallError):
    """A non-retryable provider failure (bad request, invalid credentials, ...)."""

    def __init__(self, message: str, *, provider_id: str | None = None) -> None:
        super().__init__(message, provider_id=provider_id, retryable=False)


class InvalidGrantError(NonRetryableProviderError):
    """A provider rejected the supplied credential grant as invalid (Req 19.3).

    Distinct from a generic non-retryable failure: when a Credential_Pool is
    configured for the provider, the Inference_Gateway responds to this error by
    quarantining the rejected grant and selecting another grant from the pool
    rather than advancing the fallback order. Outside a pool it behaves like any
    other non-retryable failure.
    """


@dataclass(slots=True)
class ProviderAttemptFailure:
    """Record of how a single provider failed within the call pipeline."""

    provider_id: str
    attempts: int
    error: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class _ProviderExhausted(Exception):
    """Internal control-flow signal: one provider used up its retry budget.

    Carries the :class:`ProviderAttemptFailure` record so the call pipeline can
    collect it and advance the fallback order (Req 6.3). Never escapes this
    module.
    """

    def __init__(self, failure: ProviderAttemptFailure) -> None:
        super().__init__(failure.error)
        self.failure = failure


class ProviderExhaustionError(RuntimeError):
    """Raised when every provider in the fallback order has failed (Req 6.4).

    Names every failed provider so the caller and the recorded event history can
    report exactly what was tried.
    """

    def __init__(self, failures: list[ProviderAttemptFailure]) -> None:
        self.failures = failures
        self.failed_providers = [f.provider_id for f in failures]
        if self.failed_providers:
            named = ", ".join(self.failed_providers)
            message = f"all providers failed for this model call: {named}"
        else:
            message = "no eligible providers were available for this model call"
        super().__init__(message)


# A provider call is any callable that, given a provider id, a request, and the
# run scope, returns a :class:`ModelResponse` or raises. Raising
# :class:`ProviderCallError` lets the caller signal retryability; any other
# exception is treated as retryable (transient) by default.
ProviderCall = Callable[[str, ModelRequest, RunScope], ModelResponse]

# A health provider yields the current :class:`ProviderHealth` snapshot used for
# routing. Defaults to an empty snapshot, which makes the router honor the
# configured fallback order verbatim.
HealthProvider = Callable[[], ProviderHealth]


# ---------------------------------------------------------------------------
# Budgets (Req 7.1, 7.2, 7.3, 7.5)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class BudgetDecision:
    """Outcome of a pre-call Budget check.

    ``allowed`` is always ``True`` when this is returned (a blocking decision
    raises :class:`BudgetExceededError` instead of returning). ``fail_open``
    marks the Req 7.3 case where the Budget check could not be performed because
    budget state was unavailable: the call is allowed, the skipped check is
    recorded in the run history, and ``skip_rate_limit`` instructs the gateway
    to disable Rate_Limit delays for that call.
    """

    allowed: bool = True
    fail_open: bool = False
    skip_rate_limit: bool = False


class BudgetExceededError(RuntimeError):
    """Raised when a model call would push a Workflow_Run over its Budget.

    Raising this *blocks* the call (Req 7.2). By the time it is raised the
    :class:`BudgetTracker` has already transitioned the run to the
    ``budget_exceeded`` terminal state and emitted a budget status event.
    """

    def __init__(self, scope: RunScope, budget: Budget) -> None:
        self.run_id = scope.run_id
        self.budget = budget
        super().__init__(
            f"model call blocked: run '{scope.run_id}' would exceed its budget"
        )


# A budget-state provider yields the :class:`Budget` for a scope (or ``None``
# when the scope has no configured budget). Raising signals that budget state is
# temporarily unavailable, triggering the Req 7.3 fail-open path.
BudgetStateProvider = Callable[[RunScope], "Budget | None"]


class BudgetTracker:
    """Tracks cumulative token/cost usage per Workflow_Run against its Budget.

    Responsibilities (Requirement 7):

    * **Track usage (7.1)** — :meth:`charge` accumulates the tokens and estimated
      cost actually consumed by each call and persists the running totals to the
      ``workflow_runs.budget_json`` column.
    * **Block on exceed (7.2)** — :meth:`precheck` blocks the first call that
      would carry the run over either limit by transitioning the run to the
      ``budget_exceeded`` terminal state, emitting a budget status event, and
      raising :class:`BudgetExceededError`.
    * **Fail-open (7.3)** — when budget state cannot be loaded, :meth:`precheck`
      allows the call, records the skipped check in the run history, and signals
      that Rate_Limit delays must be disabled for that call.
    * **Status events (7.5)** — both blocking and skipped checks emit a
      ``budget.status`` event through the :class:`~core.event_router.EventRouter`.

    Budget state is read through an injectable :data:`BudgetStateProvider`; the
    default reads the in-scope :class:`Budget` when present and otherwise loads
    the persisted budget for the run. Tests inject a provider that raises to
    exercise the fail-open path.
    """

    def __init__(
        self,
        state: DatabaseBackend,
        events: EventRouter,
        *,
        budget_state_provider: BudgetStateProvider | None = None,
    ) -> None:
        if state is None:
            raise ValueError("a DatabaseBackend is required")
        if events is None:
            raise ValueError("an EventRouter is required")
        self._state = state
        self._events = events
        self._provider = budget_state_provider
        self._lock = threading.RLock()

    # -- pre-call check -----------------------------------------------------

    def precheck(
        self, scope: RunScope, *, tokens: int = 0, cost: float = 0.0
    ) -> BudgetDecision:
        """Decide whether a call with the estimated ``tokens``/``cost`` may run.

        Returns a :class:`BudgetDecision` when the call is allowed (including the
        fail-open case); raises :class:`BudgetExceededError` when the call would
        exceed the run's Budget (Req 7.2).
        """
        with self._lock:
            try:
                budget = self._load_budget(scope)
            except Exception as exc:  # noqa: BLE001 - any failure => unavailable
                # Req 7.3: budget state unavailable -> fail open, record, and
                # disable rate-limit delays for this call.
                self._record_skip(scope, str(exc))
                return BudgetDecision(allowed=True, fail_open=True, skip_rate_limit=True)

            if budget is None:
                # No configured Budget for this scope: nothing to enforce.
                return BudgetDecision(allowed=True)

            if budget.would_exceed(tokens, cost):
                self._block(scope, budget)  # raises BudgetExceededError
            return BudgetDecision(allowed=True)

    # -- usage accounting (Req 7.1) ----------------------------------------

    def charge(self, scope: RunScope, *, tokens: int = 0, cost: float = 0.0) -> None:
        """Add actual usage to the run's cumulative totals and persist them."""
        with self._lock:
            try:
                budget = self._load_budget(scope)
            except Exception:  # noqa: BLE001 - cannot persist usage; proceed
                return
            if budget is None:
                return
            budget.used_tokens += int(tokens)
            budget.used_cost += float(cost)
            self._persist_usage(scope.run_id, budget)

    # -- internals ----------------------------------------------------------

    def _load_budget(self, scope: RunScope) -> Budget | None:
        """Return the current Budget for a scope or ``None`` when unconfigured.

        Raises on failure to signal that budget state is unavailable (Req 7.3).
        """
        if self._provider is not None:
            return self._provider(scope)
        if scope.budget is not None:
            return scope.budget
        row = self._state.fetch_one(
            "SELECT budget_json FROM workflow_runs WHERE id = ?", (scope.run_id,)
        )
        if row is None or not row.get("budget_json"):
            return None
        data = from_json(row["budget_json"], None)
        if not isinstance(data, dict):
            raise ValueError("malformed persisted budget state")
        return Budget(
            max_tokens=data.get("max_tokens"),
            max_cost=data.get("max_cost"),
            used_tokens=int(data.get("used_tokens", 0) or 0),
            used_cost=float(data.get("used_cost", 0.0) or 0.0),
        )

    def _block(self, scope: RunScope, budget: Budget) -> None:
        """Transition the run to ``budget_exceeded`` and emit a status event."""
        self._state.execute(
            "UPDATE workflow_runs SET state = ?, finished_at = ? WHERE id = ?",
            (RunState.BUDGET_EXCEEDED.value, now_iso(), scope.run_id),
        )
        self._events.emit(
            scope.run_id,
            WorkflowEventType.BUDGET_STATUS,
            "model call blocked: budget exceeded",
            payload={
                "blocked": True,
                "state": RunState.BUDGET_EXCEEDED.value,
                "definition_id": scope.definition_id,
                "budget": budget.to_dict(),
            },
        )
        raise BudgetExceededError(scope, budget)

    def _record_skip(self, scope: RunScope, reason: str) -> None:
        """Record a skipped Budget check in the run history (Req 7.3)."""
        self._events.emit(
            scope.run_id,
            WorkflowEventType.BUDGET_STATUS,
            "budget check skipped: budget state unavailable",
            payload={
                "skipped": True,
                "reason": reason,
                "definition_id": scope.definition_id,
            },
        )

    def _persist_usage(self, run_id: str, budget: Budget) -> None:
        self._state.execute(
            "UPDATE workflow_runs SET budget_json = ? WHERE id = ?",
            (to_json(budget.to_dict()), run_id),
        )


# ---------------------------------------------------------------------------
# Rate limiting (Req 7.4, 7.5)
# ---------------------------------------------------------------------------


class RateLimiter:
    """Bounds model calls per time window per provider and delays the excess.

    Implements a sliding-window limiter (Req 7.4): at most ``max_calls`` calls to
    a given provider are admitted within any ``window_seconds`` interval. When the
    window is full, :meth:`acquire` delays the caller until the oldest call ages
    out of the window, emitting a ``rate_limit.status`` event for each delay
    (Req 7.5).

    The clock and the sleep are injected (defaulting to :func:`time.monotonic` and
    :func:`time.sleep`) so tests drive the limiter with a mock clock and never
    wait for real time. A non-positive ``max_calls`` or ``window_seconds`` makes
    the limiter a no-op (no configured limit).
    """

    def __init__(
        self,
        events: EventRouter,
        *,
        max_calls: int = 0,
        window_seconds: float = 0.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if events is None:
            raise ValueError("an EventRouter is required")
        self._events = events
        self._max_calls = int(max_calls)
        self._window = float(window_seconds)
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.RLock()
        self._buckets: dict[str, deque[float]] = defaultdict(deque)

    def acquire(self, scope: RunScope, provider_id: str) -> float:
        """Admit one call to ``provider_id``, delaying while the window is full.

        Returns the total delay applied (``0.0`` when the call was admitted
        immediately). Emits a ``rate_limit.status`` event for each delay
        (Req 7.5).
        """
        if self._max_calls <= 0 or self._window <= 0:
            return 0.0

        total_delay = 0.0
        while True:
            with self._lock:
                now = self._clock()
                bucket = self._buckets[provider_id]
                self._evict(bucket, now)
                if len(bucket) < self._max_calls:
                    bucket.append(now)
                    return total_delay
                # Window full: wait until the oldest call leaves the window.
                wait = bucket[0] + self._window - now

            if wait <= 0:
                # Boundary already passed; re-evaluate after eviction.
                continue
            self._emit_delay(scope, provider_id, wait)
            self._sleep(wait)
            total_delay += wait

    def _evict(self, bucket: deque[float], now: float) -> None:
        cutoff = now - self._window
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()

    def _emit_delay(self, scope: RunScope, provider_id: str, wait: float) -> None:
        self._events.emit(
            scope.run_id,
            WorkflowEventType.RATE_LIMIT_STATUS,
            f"rate limit reached: delaying call to provider '{provider_id}'",
            payload={
                "provider_id": provider_id,
                "delay_seconds": wait,
                "max_calls": self._max_calls,
                "window_seconds": self._window,
                "definition_id": scope.definition_id,
            },
        )


# ---------------------------------------------------------------------------
# Credential pools (Req 6.5, 19.2, 19.3)
# ---------------------------------------------------------------------------


# A grant source issues a Kernel secret grant for a secret reference and target,
# returning a :class:`GrantContext` (grant id + session ref only, never a raw
# secret value). In production this is
# ``RustInfraExecutionManager.request_secret_grant``; tests inject a stub.
GrantSource = Callable[[str, str], GrantContext]


@dataclass(slots=True)
class QuarantinedGrant:
    """A record of a Credential_Pool grant the provider rejected as invalid.

    Retained for review (Req 19.3). Carries only references — the secret/grant
    identifiers and the rejection reason — never a raw secret value.
    """

    provider_id: str
    secret_ref: str
    grant_id: str
    reason: str
    quarantined_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CredentialPoolManager:
    """Rotates Kernel secret grants across a provider's Credential_Pool.

    Responsibilities (Requirement 19.2/19.3 and the 6.5 security invariant):

    * **Kernel-grant-only credentials (6.5)** — credentials are obtained solely
      through an injected :data:`GrantSource` (the kernel secret-grant RPC). The
      manager caches only the granted session context (:class:`GrantContext`,
      i.e. a grant id + opaque session reference) and never a raw secret value.
    * **Rotation across successive calls (19.2)** — :meth:`acquire` advances a
      round-robin cursor over the provider's configured secret references so
      successive calls to the same provider use different grants.
    * **Quarantine rejected grants (19.3)** — :meth:`quarantine` records a grant
      the provider rejected as invalid, removes it from the rotation and the
      session cache, and retains it for review via :attr:`quarantined`. Later
      acquisitions skip quarantined references and select another grant.

    Pools are configured as ``{provider_id: [secret_ref, ...]}``. A provider with
    no configured pool yields ``None`` from :meth:`acquire`, leaving the gateway
    to call that provider without a pool grant (backward compatible).
    """

    def __init__(
        self,
        grant_source: GrantSource,
        *,
        pools: dict[str, list[str]] | None = None,
    ) -> None:
        if grant_source is None:
            raise ValueError("a grant_source callable is required")
        self._grant_source = grant_source
        self._pools: dict[str, list[str]] = {
            pid: list(refs) for pid, refs in (pools or {}).items()
        }
        self._cursor: dict[str, int] = defaultdict(int)
        self._quarantined: dict[str, set[str]] = defaultdict(set)
        self._quarantine_log: list[QuarantinedGrant] = []
        # Session-context cache only (Req 6.5): (provider_id, secret_ref) ->
        # GrantContext. Never holds a raw secret value.
        self._cache: dict[tuple[str, str], GrantContext] = {}
        # Reverse map from an issued grant id to its (provider_id, secret_ref)
        # so a rejected GrantContext can be quarantined by reference.
        self._grant_refs: dict[str, tuple[str, str]] = {}
        self._lock = threading.RLock()

    def has_pool(self, provider_id: str) -> bool:
        """True when a non-empty Credential_Pool is configured for the provider."""
        return bool(self._pools.get(provider_id))

    def acquire(self, provider_id: str, *, target: str) -> GrantContext | None:
        """Return the next non-quarantined grant for ``provider_id`` (Req 19.2).

        Advances a round-robin cursor so successive calls rotate across the
        pool's grants. Reuses a cached granted session context when available
        and otherwise obtains a fresh grant through the injected grant source.
        Returns ``None`` when the provider has no pool, and raises no error when
        every grant is quarantined (returns ``None`` so the caller can surface
        pool exhaustion in its own terms).
        """
        with self._lock:
            refs = self._pools.get(provider_id)
            if not refs:
                return None
            quarantined = self._quarantined[provider_id]
            n = len(refs)
            start = self._cursor[provider_id]
            chosen_ref: str | None = None
            for offset in range(n):
                idx = (start + offset) % n
                ref = refs[idx]
                if ref not in quarantined:
                    chosen_ref = ref
                    self._cursor[provider_id] = (idx + 1) % n
                    break
            if chosen_ref is None:
                # Every grant in the pool has been quarantined (Req 19.3).
                return None

            grant = self._cache.get((provider_id, chosen_ref))
            if grant is None:
                grant = self._grant_source(chosen_ref, target)
                if grant is None or not grant.grant_id or not grant.session_ref:
                    raise RuntimeError(
                        "credential pool grant source returned no grant reference "
                        f"for secret {chosen_ref!r}; no raw-secret fallback is permitted"
                    )
                # Cache only the granted session context (Req 6.5).
                self._cache[(provider_id, chosen_ref)] = grant
            self._grant_refs[grant.grant_id] = (provider_id, chosen_ref)
            return grant

    def quarantine(self, provider_id: str, grant: GrantContext, *, reason: str = "") -> None:
        """Quarantine a rejected grant and retain it for review (Req 19.3)."""
        if grant is None:
            return
        with self._lock:
            mapping = self._grant_refs.get(grant.grant_id)
            secret_ref = mapping[1] if mapping is not None else None
            if secret_ref is None:
                for (pid, ref), cached in self._cache.items():
                    if pid == provider_id and cached.grant_id == grant.grant_id:
                        secret_ref = ref
                        break
            if secret_ref is None:
                return
            self._quarantined[provider_id].add(secret_ref)
            self._cache.pop((provider_id, secret_ref), None)
            self._quarantine_log.append(
                QuarantinedGrant(
                    provider_id=provider_id,
                    secret_ref=secret_ref,
                    grant_id=grant.grant_id,
                    reason=reason,
                    quarantined_at=now_iso(),
                )
            )

    @property
    def quarantined(self) -> list[QuarantinedGrant]:
        """The recorded rejected grants, retained for review (Req 19.3)."""
        with self._lock:
            return list(self._quarantine_log)


# ---------------------------------------------------------------------------
# Prompt cache (Req 19.4)
# ---------------------------------------------------------------------------


class PromptCache:
    """Caches prior model responses keyed by request content (Req 19.4).

    When enabled and an incoming request carries a non-empty
    :attr:`ModelRequest.cache_key` that matches a stored response, :meth:`get`
    returns that response so the gateway can short-circuit before issuing any
    new provider call. Requests without a cache key are never cached, so caching
    is strictly opt-in per request. An optional ``max_entries`` bound evicts the
    oldest entry when the cache is full (a non-positive bound is unbounded).
    """

    def __init__(self, *, enabled: bool = True, max_entries: int = 0) -> None:
        self._enabled = bool(enabled)
        self._max = int(max_entries)
        self._store: dict[str, ModelResponse] = {}
        self._order: deque[str] = deque()
        self._lock = threading.RLock()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def get(self, request: ModelRequest) -> ModelResponse | None:
        """Return the cached response for ``request`` or ``None`` on a miss."""
        if not self._enabled:
            return None
        key = getattr(request, "cache_key", "") or ""
        if not key:
            return None
        with self._lock:
            return self._store.get(key)

    def put(self, request: ModelRequest, response: ModelResponse) -> None:
        """Store ``response`` under the request's cache key (no-op without one)."""
        if not self._enabled:
            return
        key = getattr(request, "cache_key", "") or ""
        if not key:
            return
        with self._lock:
            if key not in self._store:
                if self._max > 0 and len(self._store) >= self._max:
                    oldest = self._order.popleft()
                    self._store.pop(oldest, None)
                self._order.append(key)
            self._store[key] = response


# ---------------------------------------------------------------------------
# Inference_Gateway
# ---------------------------------------------------------------------------


class InferenceGateway:
    """Single entry point for model calls with retry, fallback, and exhaustion.

    The provider invocation (``provider_call``) and the backoff clock (``sleep``)
    are injected so the pipeline can be tested deterministically and so the
    later budget/rate/cache/pool stages can wrap the same call step.
    """

    def __init__(
        self,
        router: ProviderRouter,
        events: EventRouter,
        *,
        provider_call: ProviderCall,
        default_policy: RoutingPolicy | None = None,
        health_provider: HealthProvider | None = None,
        sleep: Callable[[float], None] = time.sleep,
        base_backoff_seconds: float = 0.5,
        max_backoff_seconds: float = 30.0,
        budgets: "BudgetTracker | None" = None,
        limiter: "RateLimiter | None" = None,
        cost_estimator: Callable[[ModelRequest], tuple[int, float]] | None = None,
        cache: "PromptCache | None" = None,
        pools: "CredentialPoolManager | None" = None,
    ) -> None:
        if router is None:
            raise ValueError("a ProviderRouter is required")
        if events is None:
            raise ValueError("an EventRouter is required")
        if provider_call is None:
            raise ValueError("a provider_call callable is required")
        if base_backoff_seconds < 0 or max_backoff_seconds < 0:
            raise ValueError("backoff durations must be non-negative")
        self._router = router
        self._events = events
        self._provider_call = provider_call
        self._default_policy = default_policy or RoutingPolicy()
        self._health_provider = health_provider
        self._sleep = sleep
        self._base_backoff = base_backoff_seconds
        self._max_backoff = max_backoff_seconds
        self._budgets = budgets
        self._limiter = limiter
        self._cost_estimator = cost_estimator
        self._cache = cache
        self._pools = pools
        # Whether the injected provider_call accepts a ``grant`` argument. When
        # it does and a Credential_Pool is configured, the gateway forwards the
        # rotated grant; otherwise the kernel injects the secret via the grant
        # target and the provider_call signature stays unchanged (backward
        # compatible).
        self._provider_accepts_grant = _accepts_grant(provider_call)

    # -- public entry point -------------------------------------------------

    def call(
        self,
        request: ModelRequest,
        scope: RunScope,
        *,
        policy: RoutingPolicy | None = None,
        provider_call: ProviderCall | None = None,
    ) -> ModelResponse:
        """Execute a model call, returning the first successful response.

        Pipeline (Req 6.1–6.4): route -> for each candidate provider, retry with
        exponential backoff up to and including ``policy.max_retries`` -> on
        exhaustion advance to the next provider -> when all providers are
        exhausted, record the failure in the run history and raise
        :class:`ProviderExhaustionError`.

        Budgets, rate limits, credential pools, and prompt caching are layered
        into this method by later tasks; the provider-call-with-retry step is the
        stable core they wrap.

        ``provider_call`` optionally overrides the instance's default provider
        invocation for this single call. Callers whose "actual provider call" is
        request-specific — for example ``agent_invoker.execute_invocation``,
        which wraps a per-invocation DSPy/``build_lm`` execution — pass their own
        callable so the gateway's policy layer (routing, budget, rate limiting,
        cache, retry, fallback) wraps the real provider call rather than
        replacing it (Req 6.1). The override defaults to ``None`` so existing
        callers keep using the injected ``provider_call`` unchanged.
        """
        effective_policy = policy or self._default_policy
        effective_call = provider_call or self._provider_call

        # Prompt cache lookup precedes all provider work (Req 19.4). A hit
        # returns the stored response and issues no new provider call (and so
        # consumes no budget or rate-limit allowance).
        if self._cache is not None:
            cached = self._cache.get(request)
            if cached is not None:
                return cached

        # Budget check precedes any provider work (Req 7.1, 7.2, 7.3). Blocking
        # raises BudgetExceededError after transitioning the run; a fail-open
        # decision allows the call and disables rate-limit delays for it.
        est_tokens, est_cost = self._estimate(request)
        skip_rate_limit = False
        if self._budgets is not None:
            decision = self._budgets.precheck(scope, tokens=est_tokens, cost=est_cost)
            skip_rate_limit = decision.skip_rate_limit

        health = (
            self._health_provider() if self._health_provider is not None else ProviderHealth()
        )
        candidates = self._router.select(effective_policy, health)

        failures: list[ProviderAttemptFailure] = []
        for provider_id in candidates:
            # Rate limit per provider (Req 7.4); disabled when the budget check
            # failed open (Req 7.3).
            if self._limiter is not None and not skip_rate_limit:
                self._limiter.acquire(scope, provider_id)
            try:
                response = self._call_with_retry(
                    provider_id,
                    request,
                    scope,
                    effective_policy.max_retries,
                    effective_call,
                )
            except _ProviderExhausted as exhausted:
                # This provider is exhausted; advance the fallback order (Req 6.3).
                failure = exhausted.failure
                failures.append(failure)
                LOGGER.info(
                    "provider %s exhausted after %d attempt(s); advancing fallback",
                    failure.provider_id,
                    failure.attempts,
                )
                continue
            # Success: record actual usage against the run's Budget (Req 7.1).
            self._charge_budget(scope, response, est_tokens, est_cost)
            # Populate the prompt cache so an identical later request can be
            # served without a provider call (Req 19.4).
            if self._cache is not None:
                self._cache.put(request, response)
            return response

        # Every candidate provider failed (Req 6.4): record and raise.
        return self._exhausted(scope, failures)

    # -- per-provider retry loop -------------------------------------------

    def _call_with_retry(
        self,
        provider_id: str,
        request: ModelRequest,
        scope: RunScope,
        max_retries: int,
        provider_call: ProviderCall,
    ) -> ModelResponse:
        """Attempt one provider with bounded, inclusive exponential-backoff retry.

        Makes at most ``max_retries + 1`` attempts (Req 6.2): one initial attempt
        plus up to ``max_retries`` retries. A non-retryable error stops retrying
        immediately. On final failure raises :class:`ProviderAttemptFailure`
        describing the provider, attempt count, and last error so the caller can
        advance the fallback order.
        """
        retry_budget = max(0, max_retries)
        attempts = 0
        last_error: BaseException | None = None

        while True:
            attempts += 1
            try:
                response = self._attempt(provider_id, request, scope, provider_call)
            except Exception as exc:  # noqa: BLE001 - classified below
                last_error = exc
                retries_done = attempts - 1
                if not _is_retryable(exc) or retries_done >= retry_budget:
                    # Out of retries (or non-retryable): this provider is done.
                    raise _ProviderExhausted(
                        ProviderAttemptFailure(
                            provider_id=provider_id,
                            attempts=attempts,
                            error=str(exc),
                        )
                    ) from exc
                # Back off before the next retry (Req 6.2). ``retries_done`` is
                # the number of retries already performed; use it as the
                # exponent so the first retry waits ``base``, the second
                # ``base * 2``, and so on.
                self._sleep(self._backoff_delay(retries_done))
                continue
            else:
                return _ensure_provider_id(response, provider_id)

        # Unreachable: the loop only exits via return or raise.
        raise AssertionError("retry loop terminated unexpectedly")  # pragma: no cover

    # -- single provider attempt (credential-pool rotation) ----------------

    def _attempt(
        self,
        provider_id: str,
        request: ModelRequest,
        scope: RunScope,
        provider_call: ProviderCall,
    ) -> ModelResponse:
        """Invoke the provider once, rotating Credential_Pool grants as needed.

        When a Credential_Pool is configured for ``provider_id`` the gateway
        acquires the next rotated grant (Req 19.2) and forwards it to the
        provider call. If the provider rejects the grant as invalid
        (:class:`InvalidGrantError`), the grant is quarantined and another grant
        is selected (Req 19.3); this repeats until a grant succeeds or the pool
        is exhausted, at which point a non-retryable error advances the fallback
        order. Without a configured pool the provider is called directly,
        preserving the original behavior.
        """
        if self._pools is None or not self._pools.has_pool(provider_id):
            return self._invoke_provider(provider_id, request, scope, None, provider_call)

        target = f"inference:{provider_id}"
        while True:
            grant = self._pools.acquire(provider_id, target=target)
            if grant is None:
                # Every grant in the pool has been quarantined (Req 19.3); treat
                # the provider as failed so the fallback order advances.
                raise NonRetryableProviderError(
                    "credential pool exhausted: all grants quarantined",
                    provider_id=provider_id,
                )
            try:
                return self._invoke_provider(
                    provider_id, request, scope, grant, provider_call
                )
            except InvalidGrantError as exc:
                # Rejected grant: quarantine it and select another (Req 19.3).
                self._pools.quarantine(provider_id, grant, reason=str(exc))
                continue

    def _invoke_provider(
        self,
        provider_id: str,
        request: ModelRequest,
        scope: RunScope,
        grant: GrantContext | None,
        provider_call: ProviderCall,
    ) -> ModelResponse:
        """Call ``provider_call``, forwarding a grant when the callable accepts one."""
        if grant is not None:
            accepts_grant = (
                self._provider_accepts_grant
                if provider_call is self._provider_call
                else _accepts_grant(provider_call)
            )
            if accepts_grant:
                return provider_call(provider_id, request, scope, grant=grant)
        return provider_call(provider_id, request, scope)

    def _backoff_delay(self, exponent: int) -> float:
        """Exponential backoff delay for the given zero-based retry exponent."""
        delay = self._base_backoff * (2**exponent)
        if self._max_backoff:
            return min(delay, self._max_backoff)
        return delay

    # -- exhaustion ---------------------------------------------------------

    def _exhausted(
        self, scope: RunScope, failures: list[ProviderAttemptFailure]
    ) -> ModelResponse:
        """Record exhaustion in the run history and raise (Req 6.4)."""
        error = ProviderExhaustionError(failures)
        self._events.emit(
            scope.run_id,
            INFERENCE_EXHAUSTED_EVENT,
            str(error),
            payload={
                "definition_id": scope.definition_id,
                "failed_providers": error.failed_providers,
                "failures": [f.to_dict() for f in failures],
            },
        )
        raise error

    # -- budget helpers -----------------------------------------------------

    def _estimate(self, request: ModelRequest) -> tuple[int, float]:
        """Estimate the (tokens, cost) a request will consume for budgeting.

        Defaults to ``(0, 0.0)`` when no estimator is configured, which leaves
        the Budget check to block only when the run is already at its limit.
        """
        if self._cost_estimator is None:
            return 0, 0.0
        tokens, cost = self._cost_estimator(request)
        return int(tokens), float(cost)

    def _charge_budget(
        self, scope: RunScope, response: ModelResponse, est_tokens: int, est_cost: float
    ) -> None:
        """Charge actual usage against the run's Budget after a successful call."""
        if self._budgets is None:
            return
        tokens = response.token_usage if response.token_usage is not None else est_tokens
        self._budgets.charge(scope, tokens=tokens, cost=est_cost)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_retryable(exc: BaseException) -> bool:
    """Classify an exception raised by a provider call as retryable or not.

    :class:`ProviderCallError` carries an explicit ``retryable`` flag. Any other
    exception is treated as a transient failure (retryable) so that unexpected
    provider/transport errors still get the configured retry budget.
    """
    if isinstance(exc, ProviderCallError):
        return exc.retryable
    return True


def _ensure_provider_id(response: ModelResponse, provider_id: str) -> ModelResponse:
    """Stamp the serving provider id onto the response when absent."""
    if isinstance(response, ModelResponse) and not response.provider_id:
        response.provider_id = provider_id
    return response


def _accepts_grant(provider_call: ProviderCall) -> bool:
    """Whether ``provider_call`` accepts a ``grant`` keyword argument.

    Lets the gateway forward a rotated Credential_Pool grant only to providers
    that opt in, keeping the original three-argument provider-call contract
    working unchanged (backward compatible).
    """
    try:
        signature = inspect.signature(provider_call)
    except (TypeError, ValueError):
        return False
    for parameter in signature.parameters.values():
        if parameter.kind is inspect.Parameter.VAR_KEYWORD:
            return True
        if parameter.name == "grant" and parameter.kind in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        ):
            return True
    return False
