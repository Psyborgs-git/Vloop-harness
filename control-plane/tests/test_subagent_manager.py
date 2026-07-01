"""Unit tests for Subagent_Manager (task 26.1).

Covers isolated spawn (Req 15.1), toolset restriction (Req 15.2), the
concurrency bound with queuing of excess requests (Req 15.3), and returning the
result to the parent while recording token usage against the run (Req 15.4).

The property test (task 26.2) lives in its own file; these are example-based
unit tests with a deterministic, injectable subagent runner.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from core.database import SQLiteBackend
from core.helpers import from_json, now_iso
from core.subagent_manager import (
    SubagentContext,
    SubagentManager,
    SubagentResult,
    SubagentSpec,
)


@pytest.fixture()
def backend(tmp_path: Path) -> SQLiteBackend:
    return SQLiteBackend(tmp_path / "subagent-test.db")


def _insert_run(backend: SQLiteBackend, run_id: str, budget_json: str | None = None) -> None:
    ts = now_iso()
    backend.execute(
        "INSERT INTO workflow_runs "
        "(id, definition_id, state, concurrency_limit, budget_json, "
        "created_at, started_at, finished_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, "def-1", "running", 4, budget_json, ts, ts, None),
    )


# -- isolation (Req 15.1) ---------------------------------------------------


def test_subagent_context_is_isolated_from_parent() -> None:
    parent_context = {"shared": {"count": 1}, "items": [1, 2]}

    def runner(ctx: SubagentContext) -> SubagentResult:
        # Mutate the child's view; this must not affect the parent.
        ctx.context["shared"]["count"] = 999
        ctx.context["items"].append(3)
        ctx.context["new_key"] = "child-only"
        return SubagentResult(run_id=ctx.run_id, output="done")

    manager = SubagentManager(runner)
    manager.spawn(SubagentSpec(run_id="run-1", task="t", context=parent_context))

    # Parent context is untouched after the child mutated its isolated copy.
    assert parent_context == {"shared": {"count": 1}, "items": [1, 2]}


# -- toolset restriction (Req 15.2) -----------------------------------------


def test_subagent_restricted_to_granted_toolset() -> None:
    seen: dict[str, object] = {}

    def runner(ctx: SubagentContext) -> SubagentResult:
        seen["toolset"] = ctx.toolset
        seen["allows_fs"] = ctx.allows("fs")
        seen["allows_net"] = ctx.allows("net")
        return SubagentResult(run_id=ctx.run_id)

    manager = SubagentManager(runner)
    manager.spawn(SubagentSpec(run_id="run-1", toolset=["fs", "git"]))

    assert seen["toolset"] == frozenset({"fs", "git"})
    assert seen["allows_fs"] is True
    assert seen["allows_net"] is False


# -- concurrency bound + queuing (Req 15.3) ---------------------------------


def test_concurrency_bound_is_never_exceeded_and_excess_is_queued() -> None:
    limit = 2
    total = 6
    barrier_lock = threading.Lock()
    observed_peak = {"value": 0}
    active = {"value": 0}
    release = threading.Event()

    def runner(ctx: SubagentContext) -> SubagentResult:
        with barrier_lock:
            active["value"] += 1
            observed_peak["value"] = max(observed_peak["value"], active["value"])
        # Hold the slot until the test lets it go, forcing contention so the
        # bound is genuinely exercised (excess specs must queue).
        release.wait(timeout=5)
        with barrier_lock:
            active["value"] -= 1
        return SubagentResult(run_id=ctx.run_id, token_usage=1)

    manager = SubagentManager(runner, concurrency_limit=limit)
    specs = [SubagentSpec(run_id="run-1", task=f"t{i}") for i in range(total)]

    worker = threading.Thread(target=manager.spawn_many, args=(specs,))
    worker.start()

    # Give the manager time to fill its slots, then confirm it never exceeds
    # the limit while work is queued behind the held slots.
    threading.Event().wait(0.2)
    assert manager.active_count <= limit
    release.set()
    worker.join(timeout=10)

    assert observed_peak["value"] <= limit
    assert manager.peak_active <= limit


def test_spawn_many_returns_results_in_input_order() -> None:
    def runner(ctx: SubagentContext) -> SubagentResult:
        return SubagentResult(run_id=ctx.run_id, output=ctx.task)

    manager = SubagentManager(runner, concurrency_limit=3)
    specs = [SubagentSpec(run_id="run-1", task=f"task-{i}") for i in range(10)]

    results = manager.spawn_many(specs)

    assert [r.output for r in results] == [f"task-{i}" for i in range(10)]


# -- result return + usage accounting (Req 15.4) ----------------------------


def test_result_is_returned_to_parent() -> None:
    def runner(ctx: SubagentContext) -> SubagentResult:
        return SubagentResult(run_id=ctx.run_id, output={"answer": 42}, token_usage=7)

    manager = SubagentManager(runner)
    result = manager.spawn(SubagentSpec(run_id="run-1"))

    assert result.output == {"answer": 42}
    assert result.ok is True
    assert result.token_usage == 7


def test_usage_is_accumulated_in_memory_per_run() -> None:
    def runner(ctx: SubagentContext) -> SubagentResult:
        return SubagentResult(run_id=ctx.run_id, token_usage=5)

    manager = SubagentManager(runner, concurrency_limit=4)
    manager.spawn_many([SubagentSpec(run_id="run-1") for _ in range(3)])
    manager.spawn(SubagentSpec(run_id="run-2"))

    assert manager.usage_for("run-1") == 15
    assert manager.usage_for("run-2") == 5
    assert manager.usage_for("unknown") == 0


def test_usage_is_persisted_against_the_run_budget(backend: SQLiteBackend) -> None:
    _insert_run(backend, "run-1")

    def runner(ctx: SubagentContext) -> SubagentResult:
        return SubagentResult(run_id=ctx.run_id, token_usage=8)

    manager = SubagentManager(runner, concurrency_limit=2, state=backend)
    manager.spawn(SubagentSpec(run_id="run-1"))
    manager.spawn(SubagentSpec(run_id="run-1"))

    row = backend.fetch_one(
        "SELECT budget_json FROM workflow_runs WHERE id = ?", ("run-1",)
    )
    budget = from_json(row["budget_json"], {})
    assert budget["used_tokens"] == 16


def test_usage_persistence_preserves_existing_budget_limits(
    backend: SQLiteBackend,
) -> None:
    _insert_run(
        backend,
        "run-1",
        budget_json='{"max_tokens": 100, "max_cost": 5.0, "used_tokens": 10, "used_cost": 1.5}',
    )

    def runner(ctx: SubagentContext) -> SubagentResult:
        return SubagentResult(run_id=ctx.run_id, token_usage=4)

    manager = SubagentManager(runner, state=backend)
    manager.spawn(SubagentSpec(run_id="run-1"))

    row = backend.fetch_one(
        "SELECT budget_json FROM workflow_runs WHERE id = ?", ("run-1",)
    )
    budget = from_json(row["budget_json"], {})
    assert budget["used_tokens"] == 14
    assert budget["max_tokens"] == 100
    assert budget["max_cost"] == 5.0
    assert budget["used_cost"] == 1.5


# -- failure handling -------------------------------------------------------


def test_runner_exception_becomes_a_failed_result() -> None:
    def runner(ctx: SubagentContext) -> SubagentResult:
        raise RuntimeError("boom")

    manager = SubagentManager(runner)
    result = manager.spawn(SubagentSpec(run_id="run-1", toolset=["fs"]))

    assert result.ok is False
    assert result.error_message == "boom"
    assert result.toolset == frozenset({"fs"})


def test_runner_is_required() -> None:
    with pytest.raises(ValueError):
        SubagentManager(None)  # type: ignore[arg-type]
