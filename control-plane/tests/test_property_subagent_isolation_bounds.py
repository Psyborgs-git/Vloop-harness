"""Property-based test for Subagent_Manager isolation and bounds.

# Feature: orchestration-engine-completion, Property 37: Subagent isolation, toolset restriction, concurrency bound, and accounting

Property 37 states that *for any* batch of subagent spawns, the
Subagent_Manager guarantees all four delegation invariants at once:

* **Isolation (Req 15.1).** Each subagent runs against a deep copy of the
  parent's context; mutations a child makes to its own context never leak back
  to the parent.
* **Toolset restriction (Req 15.2).** Each subagent's allowed toolset equals
  exactly the set granted at spawn time — no more, no less.
* **Concurrency bound (Req 15.3).** Across concurrent spawns the number of
  subagents running at once never exceeds the configured concurrency limit;
  excess requests queue until a slot frees.
* **Usage accounting (Req 15.4).** On completion each subagent's token usage is
  recorded against its run, so ``usage_for(run_id)`` equals the sum of that
  run's per-spawn token usages in the batch.

The test generates random batches of :class:`SubagentSpec` with random
toolsets, nested mutable contexts, per-spawn token usages, run ids, and a random
``concurrency_limit``. A deterministic, thread-safe runner mutates the child's
isolated context (to exercise isolation) and echoes the granted toolset and the
spec's intended usage. After spawning the whole batch concurrently the four
invariants above are asserted.

**Validates: Requirements 15.1, 15.2, 15.3, 15.4**
"""

from __future__ import annotations

import copy
import string
import threading
import time
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.subagent_manager import (
    SubagentContext,
    SubagentManager,
    SubagentResult,
    SubagentSpec,
)

# ---------------------------------------------------------------------------
# Strategies: random batches of subagent specs + a concurrency limit
# ---------------------------------------------------------------------------

_IDENT = st.text(
    alphabet=string.ascii_letters + string.digits + "_", min_size=1, max_size=6
)

# A small pool of run ids so a batch reliably groups several spawns under the
# same run, making the per-run accounting assertion meaningful.
_RUN_IDS = st.sampled_from(["run-a", "run-b", "run-c"])

# Toolset names drawn from a fixed alphabet so distinct grants are common.
_TOOLSETS = st.lists(
    st.sampled_from(["fs", "net", "git", "shell", "db", "http", "mem"]),
    min_size=0,
    max_size=5,
    unique=True,
)

# Nested, mutable context values: the runner will mutate these in place, so they
# must contain reference types (dicts/lists) for the isolation check to bite.
_CONTEXT = st.dictionaries(
    keys=_IDENT,
    values=st.recursive(
        st.integers() | st.text(max_size=4) | st.booleans(),
        lambda children: st.lists(children, max_size=3)
        | st.dictionaries(_IDENT, children, max_size=3),
        max_leaves=6,
    ),
    max_size=4,
)


@st.composite
def batches(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a random batch of subagent specs plus a concurrency limit."""
    size = draw(st.integers(min_value=1, max_value=8))
    specs: list[SubagentSpec] = []
    for index in range(size):
        specs.append(
            SubagentSpec(
                run_id=draw(_RUN_IDS),
                task=f"task-{index}",
                toolset=draw(_TOOLSETS),
                context=draw(_CONTEXT),
            )
        )
    usages = draw(
        st.lists(
            st.integers(min_value=0, max_value=1000),
            min_size=size,
            max_size=size,
        )
    )
    concurrency_limit = draw(st.integers(min_value=1, max_value=6))
    return {
        "specs": specs,
        "usages": usages,
        "concurrency_limit": concurrency_limit,
    }


# ---------------------------------------------------------------------------
# Property 37
# ---------------------------------------------------------------------------


# deadline=None: each example spins up worker threads whose timing varies; the
# property is about the four invariants, not latency.
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(case=batches())
def test_subagent_isolation_toolset_concurrency_and_accounting(
    case: dict[str, Any],
) -> None:
    specs: list[SubagentSpec] = case["specs"]
    usages: list[int] = case["usages"]
    concurrency_limit: int = case["concurrency_limit"]

    # Snapshot the original parent contexts so the isolation check can confirm
    # they were never mutated by any child.
    original_contexts = [copy.deepcopy(dict(spec.context)) for spec in specs]

    # Map each spec (by identity/order) to the token usage it should report.
    usage_by_spec_index = {id(spec): usages[i] for i, spec in enumerate(specs)}

    # Records what each runner invocation observed, keyed by task (unique per
    # spec), so toolset-restriction can be checked per subagent after the run.
    observed_toolsets: dict[str, frozenset[str]] = {}
    observed_lock = threading.Lock()

    def runner(ctx: SubagentContext) -> SubagentResult:
        # Exercise isolation: aggressively mutate the child's own context. If
        # the manager handed out a shared reference this would corrupt the
        # parent snapshot and the assertion below would fail.
        ctx.context["__child_mutation__"] = "child-only"
        for key in list(ctx.context.keys()):
            value = ctx.context[key]
            if isinstance(value, dict):
                value["__nested__"] = True
            elif isinstance(value, list):
                value.append("__appended__")

        with observed_lock:
            observed_toolsets[ctx.task] = ctx.toolset

        # Widen the concurrency window so independent spawns actually overlap,
        # genuinely exercising the bound rather than running serially.
        time.sleep(0.001)

        # Echo the granted toolset and report this spec's intended token usage.
        # The runner finds its usage via the task suffix index.
        index = int(ctx.task.split("-")[-1])
        return SubagentResult(
            run_id=ctx.run_id,
            output=ctx.task,
            token_usage=usages[index],
            toolset=ctx.toolset,
        )

    manager = SubagentManager(runner, concurrency_limit=concurrency_limit)
    results = manager.spawn_many(specs)

    # -- Req 15.1: isolation — parent contexts are untouched by any child.
    for spec, original in zip(specs, original_contexts):
        assert dict(spec.context) == original

    # -- Req 15.2: each subagent's allowed toolset equals exactly the grant.
    assert len(results) == len(specs)
    for spec, result in zip(specs, results):
        expected = frozenset(spec.toolset)
        # The result echoes the granted scope...
        assert result.toolset == expected
        # ...and what the runner actually saw inside the isolated context
        # equals exactly the granted set (nothing added, nothing removed).
        assert observed_toolsets[spec.task] == expected

    # -- Req 15.3: peak concurrency never exceeded the configured limit.
    assert manager.peak_active <= concurrency_limit

    # -- Req 15.4: usage_for(run_id) equals the per-run sum of token usages.
    expected_usage: dict[str, int] = {}
    for spec in specs:
        expected_usage[spec.run_id] = (
            expected_usage.get(spec.run_id, 0)
            + usage_by_spec_index[id(spec)]
        )
    for run_id, total in expected_usage.items():
        assert manager.usage_for(run_id) == total
