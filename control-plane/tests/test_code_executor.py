"""Unit tests for core.code_executor (sandboxed script submission).

Covers the task 20.1 behaviors: sandbox-only submission with no host fallback,
captured stdout/stderr/exit-code passthrough, time-limit enforcement via
workload teardown, and least-privilege toolset/grant scoping.
"""

from __future__ import annotations

import pytest

from adapters.rust_infra import SandboxRoutingError
from core.code_executor import CodeExecutor, ExecutionResult, ScriptRequest
from core.orchestration_types import GrantContext, RunScope


class FakeExecutionManager:
    """A minimal stand-in for RustInfraExecutionManager.

    Records the spec/policy it was dispatched and replays a scripted sequence
    of log entries. Optionally raises on dispatch to model routing failure.
    """

    def __init__(self, *, log_entries=None, dispatch_error=None, job_id="job-1"):
        self._log_entries = list(log_entries or ())
        self._dispatch_error = dispatch_error
        self._job_id = job_id
        self.dispatched = None  # (spec, policy)
        self.torn_down = []

    def dispatch_job(self, spec, policy):
        self.dispatched = (spec, policy)
        if self._dispatch_error is not None:
            raise self._dispatch_error
        return self._job_id

    def stream_logs(self, job_id):
        for entry in self._log_entries:
            yield entry

    def teardown(self, job_id):
        self.torn_down.append(job_id)


def _run_scope():
    return RunScope(run_id="run-123", definition_id="def-456")


def test_dispatches_to_sandbox_and_returns_captured_output():
    manager = FakeExecutionManager(
        log_entries=[
            {"stream": "stdout", "line": "hello"},
            {"stream": "stderr", "line": "a warning"},
            {"stream": "stdout", "line": "world"},
            {"stream": "exit", "line": "0"},
        ]
    )
    executor = CodeExecutor(manager)

    result = executor.execute(
        ScriptRequest(command=["python", "script.py"], image="py:3.12"),
        _run_scope(),
    )

    assert isinstance(result, ExecutionResult)
    assert result.stdout == "hello\nworld"
    assert result.stderr == "a warning"
    assert result.exit_code == 0
    assert result.timed_out is False
    assert result.ok is True
    # The job was routed to a sandbox, not the host.
    assert manager.dispatched is not None
    spec, _policy = manager.dispatched
    assert spec["command"] == ["python", "script.py"]
    assert spec["image"] == "py:3.12"


def test_nonzero_exit_code_is_passed_through_unchanged():
    manager = FakeExecutionManager(
        log_entries=[
            {"stream": "stderr", "line": "boom"},
            {"stream": "exit", "line": "42"},
        ]
    )
    executor = CodeExecutor(manager)

    result = executor.execute(ScriptRequest(command=["./run"]), _run_scope())

    assert result.exit_code == 42
    assert result.stderr == "boom"
    assert result.ok is False


def test_routing_failure_propagates_with_no_host_fallback():
    manager = FakeExecutionManager(
        dispatch_error=SandboxRoutingError("no sandbox available")
    )
    executor = CodeExecutor(manager)

    with pytest.raises(SandboxRoutingError):
        executor.execute(ScriptRequest(command=["./run"]), _run_scope())

    # Nothing was torn down and no alternate path ran.
    assert manager.torn_down == []


def test_empty_job_id_blocks_execution():
    manager = FakeExecutionManager(job_id="")
    executor = CodeExecutor(manager)

    with pytest.raises(SandboxRoutingError):
        executor.execute(ScriptRequest(command=["./run"]), _run_scope())


def test_timeout_requests_teardown_and_returns_timeout_error():
    # Clock advances past the 1s limit while logs are being drained.
    ticks = iter([0.0, 0.5, 2.0, 2.0, 2.0])

    def clock():
        return next(ticks)

    manager = FakeExecutionManager(
        log_entries=[
            {"stream": "stdout", "line": "partial"},
            {"stream": "stdout", "line": "never reached"},
            {"stream": "exit", "line": "0"},
        ]
    )
    executor = CodeExecutor(manager, clock=clock)

    result = executor.execute(
        ScriptRequest(command=["./slow"], time_limit_seconds=1.0),
        _run_scope(),
    )

    assert result.timed_out is True
    assert result.exit_code is None
    assert result.ok is False
    assert "time limit" in (result.error_message or "")
    # The sandbox workload was terminated.
    assert manager.torn_down == ["job-1"]
    # Only the output captured before the breach is surfaced.
    assert result.stdout == "partial"


def test_sandbox_receives_only_configured_toolsets_and_grants():
    manager = FakeExecutionManager(log_entries=[{"stream": "exit", "line": "0"}])
    executor = CodeExecutor(manager)

    grants = [
        GrantContext(grant_id="g-1", session_ref="s-1"),
        GrantContext(grant_id="g-2", session_ref="s-2"),
    ]
    executor.execute(
        ScriptRequest(command=["./run"]),
        _run_scope(),
        toolsets=["fs", "net"],
        secret_grants=grants,
    )

    _spec, policy = manager.dispatched
    assert policy["toolsets"] == ["fs", "net"]
    assert policy["secret_grants"] == [
        {"grant_id": "g-1", "session_ref": "s-1"},
        {"grant_id": "g-2", "session_ref": "s-2"},
    ]
    assert policy["run_id"] == "run-123"
    assert policy["definition_id"] == "def-456"


def test_no_grants_or_toolsets_yields_empty_scoping():
    manager = FakeExecutionManager(log_entries=[{"stream": "exit", "line": "0"}])
    executor = CodeExecutor(manager)

    executor.execute(ScriptRequest(command=["./run"]), _run_scope())

    _spec, policy = manager.dispatched
    assert policy["toolsets"] == []
    assert policy["secret_grants"] == []


def test_non_positive_time_limit_is_rejected():
    manager = FakeExecutionManager()
    executor = CodeExecutor(manager)

    with pytest.raises(ValueError):
        executor.execute(
            ScriptRequest(command=["./run"], time_limit_seconds=0),
            _run_scope(),
        )


def test_requires_an_execution_manager():
    with pytest.raises(ValueError):
        CodeExecutor(None)
