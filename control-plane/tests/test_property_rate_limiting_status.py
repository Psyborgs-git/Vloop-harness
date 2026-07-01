"""Property-based test for rate limiting bounds and status events.

# Feature: orchestration-engine-completion, Property 22: Rate limiting bounds calls per window and emits status

Property 22 states that *for any* configured per-provider rate limit
(``max_calls`` per ``window_seconds``) and *any* sequence of ``acquire`` calls,
the :class:`RateLimiter` upholds three invariants:

* **Window bound (Req 7.4).** Within any window of length ``window_seconds`` no
  more than ``max_calls`` calls are admitted to a given provider. The test
  records the fake-clock timestamp at which each call is admitted and checks the
  trailing window ``(t - window_seconds, t]`` ending at every admission never
  contains more than ``max_calls`` admits.
* **Excess is delayed (Req 7.4).** A call that cannot be admitted immediately is
  delayed: ``acquire`` returns a positive delay and the injected ``sleep`` is
  invoked for exactly that amount. A call admitted immediately returns ``0.0``
  and triggers no sleep.
* **Status emitted on each delay (Req 7.5).** Every delay segment emits exactly
  one ``rate_limit.status`` event, so the number of emitted status events equals
  the number of ``sleep`` invocations.

The limiter is driven by a mock clock whose ``sleep`` advances the fake time, so
the test never waits for real time. Random ``max_calls``, ``window_seconds``, a
pool of providers, and a sequence of acquire/elapse operations are generated;
all times are whole numbers so the trailing-window arithmetic is exact at the
inclusive eviction boundary.

**Validates: Requirements 7.4, 7.5**
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.database import SQLiteBackend
from core.event_router import EventRouter, WorkflowEventType
from core.inference_gateway import RateLimiter
from core.orchestration_types import RunScope

RUN_ID = "run-prop-22"


# ---------------------------------------------------------------------------
# Mock clock: a controllable monotonic clock whose sleep advances fake time.
# ---------------------------------------------------------------------------


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


# ---------------------------------------------------------------------------
# Strategy: a rate-limit config plus a sequence of acquire / elapse operations.
# ---------------------------------------------------------------------------


@st.composite
def rate_limit_cases(draw: st.DrawFn) -> dict[str, Any]:
    max_calls = draw(st.integers(min_value=1, max_value=5))
    window_seconds = draw(st.integers(min_value=1, max_value=20))
    provider_count = draw(st.integers(min_value=1, max_value=3))
    providers = [f"p{i}" for i in range(provider_count)]

    size = draw(st.integers(min_value=1, max_value=30))
    ops: list[dict[str, Any]] = []
    for _ in range(size):
        ops.append(
            {
                "kind": draw(st.sampled_from(["acquire", "acquire", "elapse"])),
                "provider": draw(st.sampled_from(providers)),
                # External time advance (not via sleep) for the "elapse" op.
                "elapse": draw(st.integers(min_value=0, max_value=2 * window_seconds)),
            }
        )
    return {
        "max_calls": max_calls,
        "window_seconds": window_seconds,
        "ops": ops,
    }


# ---------------------------------------------------------------------------
# Property 22
# ---------------------------------------------------------------------------


@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(case=rate_limit_cases())
def test_rate_limiting_bounds_calls_per_window_and_emits_status(case: dict[str, Any]) -> None:
    max_calls: int = case["max_calls"]
    window: float = float(case["window_seconds"])
    ops: list[dict[str, Any]] = case["ops"]

    with tempfile.TemporaryDirectory() as tmp:
        backend = SQLiteBackend(Path(tmp) / "rate-prop.db")
        events = EventRouter(backend)
        clock = _FakeClock()
        limiter = RateLimiter(
            events,
            max_calls=max_calls,
            window_seconds=window,
            clock=clock.time,
            sleep=clock.sleep,
        )
        scope = RunScope(run_id=RUN_ID, definition_id="def-1", budget=None)

        # Admission timestamps per provider, in admission order.
        admits: dict[str, list[float]] = {}

        for op in ops:
            if op["kind"] == "elapse":
                # Time passes independently of the limiter (no sleep involved).
                clock.now += op["elapse"]
                continue

            provider = op["provider"]
            sleeps_before = len(clock.slept)

            delay = limiter.acquire(scope, provider)

            new_sleeps = clock.slept[sleeps_before:]
            admit_time = clock.now  # the call is admitted at the current fake time

            # -- excess is delayed (Req 7.4) ---------------------------------
            # A positive returned delay must correspond to actual sleeping that
            # sums to exactly that delay; a zero delay must not sleep at all.
            assert delay >= 0.0
            assert sum(new_sleeps) == delay
            assert (delay > 0.0) == (len(new_sleeps) > 0)
            assert all(s > 0.0 for s in new_sleeps)

            admits.setdefault(provider, []).append(admit_time)

        # -- window bound (Req 7.4) ------------------------------------------
        # For every admission at time t, the trailing window (t - window, t]
        # contains at most max_calls admits for that provider.
        for provider, times in admits.items():
            for k, t_k in enumerate(times):
                in_window = [
                    t_j for t_j in times[: k + 1] if t_j > t_k - window
                ]
                assert len(in_window) <= max_calls, (
                    f"provider {provider}: {len(in_window)} admits in window "
                    f"ending at {t_k} exceeds max_calls={max_calls}"
                )

        # -- status emitted on each delay (Req 7.5) --------------------------
        # Exactly one rate_limit.status event per sleep (delay segment).
        status_events = [
            e
            for e in events.history(RUN_ID)
            if e.type == WorkflowEventType.RATE_LIMIT_STATUS
        ]
        assert len(status_events) == len(clock.slept)
        for event in status_events:
            assert event.run_id == RUN_ID
            assert event.payload.get("delay_seconds", 0) > 0
