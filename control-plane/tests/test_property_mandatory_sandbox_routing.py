"""Property-based test for mandatory Kernel-managed Sandbox routing.

# Feature: orchestration-engine-completion, Property 25: Mutating tools and submitted scripts always route through a Sandbox

Property 25 states that *for any* tool that performs filesystem mutation or
command execution, and *for any* script submitted for execution, execution is
routed through a Kernel-managed Sandbox and is never executed on the host.

This file exercises both halves of that property across many randomly generated
inputs:

* **Submitted scripts.** Every :meth:`core.code_executor.CodeExecutor.execute`
  call dispatches the job through the injected sandbox execution manager's
  ``dispatch_job`` surface (the only execution path it has) and never through a
  host path. When sandbox routing fails the call is blocked with
  :class:`~adapters.rust_infra.SandboxRoutingError` and no alternate path runs
  (Requirements 16.1, 21.1).
* **Mutating tools.** Every mutating tool invoked through
  :class:`core.tool_registry.ToolRegistry` is routed through the injected
  ``sandbox_executor`` and never through its in-process handler. When no sandbox
  executor is available the invocation is blocked with
  :class:`~core.tool_registry.SandboxRoutingBlocked` — there is no host fallback
  and the in-process handler is never run (Requirement 9.5).

**Validates: Requirements 9.5, 16.1, 21.1**
"""

from __future__ import annotations

import string

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from adapters.rust_infra import SandboxRoutingError
from core.code_executor import CodeExecutor, ScriptRequest
from core.orchestration_types import RunScope, ToolScope, ToolSpec
from core.tool_registry import SandboxRoutingBlocked, ToolRegistry

# ---------------------------------------------------------------------------
# Recording sandbox execution manager (script path)
# ---------------------------------------------------------------------------


class RecordingSandboxManager:
    """A sandbox execution manager that records every ``dispatch_job`` call.

    It exposes only the sandbox surface (``dispatch_job``/``stream_logs``/
    ``teardown``) — there is no host execution method — so the strongest
    observable signal of host execution is simply the absence of a sandbox
    dispatch. The replayed log stream always carries a terminal exit line so
    :meth:`CodeExecutor.execute` returns a normal result. When ``fail`` is set,
    dispatch raises :class:`SandboxRoutingError` to model a routing failure.
    """

    def __init__(self, *, fail: bool = False, job_id: str = "job-1") -> None:
        self._fail = fail
        self._job_id = job_id
        self.dispatch_calls: list[tuple[dict, dict]] = []
        self.torn_down: list[str] = []

    def dispatch_job(self, spec, policy):
        self.dispatch_calls.append((dict(spec), dict(policy)))
        if self._fail:
            raise SandboxRoutingError("no sandbox available")
        return self._job_id

    def stream_logs(self, job_id):
        yield {"stream": "stdout", "line": "captured"}
        yield {"stream": "exit", "line": "0"}

    def teardown(self, job_id):
        self.torn_down.append(job_id)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_identifiers = st.text(
    alphabet=string.ascii_letters + string.digits + "_", min_size=1, max_size=16
)

_arg_values = st.one_of(
    st.text(max_size=12),
    st.integers(),
    st.booleans(),
    st.none(),
)

_tool_args = st.dictionaries(_identifiers, _arg_values, max_size=4)


@st.composite
def script_requests(draw: st.DrawFn) -> ScriptRequest:
    """Generate a random agent-authored script submission.

    Commands are non-empty argv lists; image, environment, and an optional
    positive time limit vary so the dispatch path is exercised across the input
    space.
    """
    command = draw(
        st.lists(st.text(min_size=1, max_size=12), min_size=1, max_size=5)
    )
    image = draw(st.text(max_size=12))
    environment = draw(
        st.dictionaries(_identifiers, st.text(max_size=12), max_size=3)
    )
    time_limit = draw(
        st.one_of(st.none(), st.floats(min_value=0.1, max_value=1_000.0))
    )
    sandbox_class = draw(st.sampled_from(["worker", "builder", "service"]))
    return ScriptRequest(
        command=command,
        image=image,
        environment=environment,
        time_limit_seconds=time_limit,
        sandbox_class=sandbox_class,
    )


@st.composite
def mutating_tools(draw: st.DrawFn) -> ToolSpec:
    """Generate a random mutating tool (one that must run in a Sandbox)."""
    return ToolSpec(
        name=draw(_identifiers),
        description=draw(st.text(max_size=24)),
        toolset=draw(_identifiers),
        mutating=True,
    )


def _run_scope() -> RunScope:
    return RunScope(run_id="run-123", definition_id="def-456")


# ---------------------------------------------------------------------------
# Property 25a: submitted scripts always route through the sandbox manager
# ---------------------------------------------------------------------------


@settings(
    max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow]
)
@given(request=script_requests())
def test_submitted_scripts_always_dispatch_through_sandbox(
    request: ScriptRequest,
) -> None:
    """Every executed script is dispatched through the sandbox execution
    manager exactly once, with no host path."""
    manager = RecordingSandboxManager()
    executor = CodeExecutor(manager)

    result = executor.execute(request, _run_scope())

    # The job went through the sandbox manager's dispatch surface — the only
    # execution path the executor has — exactly once.
    assert len(manager.dispatch_calls) == 1
    spec, policy = manager.dispatch_calls[0]
    assert spec["command"] == list(request.command)
    assert spec["image"] == request.image
    # The result's job id is the sandbox-issued id, proving the captured output
    # came from the sandbox and not an in-process run.
    assert result.job_id == "job-1"


@settings(
    max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow]
)
@given(request=script_requests())
def test_script_routing_failure_blocks_with_no_host_fallback(
    request: ScriptRequest,
) -> None:
    """When sandbox routing fails the script is blocked entirely; no host path
    runs and nothing is silently completed."""
    manager = RecordingSandboxManager(fail=True)
    executor = CodeExecutor(manager)

    with pytest.raises(SandboxRoutingError):
        executor.execute(request, _run_scope())

    # The executor attempted exactly one sandbox dispatch and then propagated
    # the failure — there was no fallback execution and no teardown of a
    # phantom workload.
    assert len(manager.dispatch_calls) == 1
    assert manager.torn_down == []


# ---------------------------------------------------------------------------
# Property 25b: mutating tools always route through the sandbox executor
# ---------------------------------------------------------------------------


@settings(
    max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow]
)
@given(tool=mutating_tools(), args=_tool_args)
def test_mutating_tools_always_route_through_sandbox_executor(
    tool: ToolSpec, args: dict
) -> None:
    """Every enabled mutating tool runs through the injected sandbox executor
    and never through its in-process handler."""
    sandbox_calls: list[tuple[ToolSpec, dict, RunScope | None]] = []
    host_calls: list[dict] = []

    def sandbox_executor(spec, invocation_args, run_scope):
        sandbox_calls.append((spec, invocation_args, run_scope))
        return {"ran_in": "sandbox", "tool": spec.name}

    def poison_handler(invocation_args):
        # A mutating tool must never reach the in-process handler; if it does,
        # record it so the assertion below fails loudly.
        host_calls.append(invocation_args)
        return {"ran_in": "host"}

    registry = ToolRegistry(sandbox_executor=sandbox_executor)
    registry.register_tool(tool, handler=poison_handler)
    scope = ToolScope(run_enabled={tool.toolset: True})
    run_scope = _run_scope()

    result = registry.invoke(tool.name, args, scope, run_scope=run_scope)

    # Routed through the sandbox executor exactly once...
    assert len(sandbox_calls) == 1
    assert sandbox_calls[0][0] is tool
    assert sandbox_calls[0][2] is run_scope
    # ...and never through the in-process host handler.
    assert host_calls == []
    assert result.ok is True
    assert result.sandboxed is True


@settings(
    max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow]
)
@given(tool=mutating_tools(), args=_tool_args)
def test_mutating_tools_block_when_no_sandbox_executor(
    tool: ToolSpec, args: dict
) -> None:
    """A mutating tool with no available sandbox executor is blocked with no
    host fallback; the in-process handler is never run."""
    host_calls: list[dict] = []

    def poison_handler(invocation_args):
        host_calls.append(invocation_args)
        return {"ran_in": "host"}

    registry = ToolRegistry(sandbox_executor=None)
    registry.register_tool(tool, handler=poison_handler)
    scope = ToolScope(run_enabled={tool.toolset: True})

    with pytest.raises(SandboxRoutingBlocked):
        registry.invoke(tool.name, args, scope, run_scope=_run_scope())

    # Blocked entirely — the host handler was never invoked.
    assert host_calls == []
