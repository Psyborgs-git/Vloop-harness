"""Property-based test for Code_Executor captured-output passthrough.

# Feature: orchestration-engine-completion, Property 38: Code executor returns the captured sandbox output

Property 38 states that *for any* Sandbox execution output, the Code_Executor
returns the captured stdout, stderr, and exit code unchanged to the requesting
agent.

The kernel log channel is line-oriented: the sandbox runner emits
``WorkflowLogLine``-style entries, each carrying a ``stream`` label
(``"stdout"`` / ``"stderr"``) and a ``line``, and a single terminal control
line on the ``"exit"`` channel whose ``line`` is the decimal exit code. The
:class:`~core.code_executor.CodeExecutor` reconstructs the result from this
stream.

This test feeds randomly interleaved stdout/stderr lines plus a random exit
code through a fake execution manager's ``stream_logs`` and asserts the
resulting :class:`~core.code_executor.ExecutionResult` carries:

* ``stdout`` equal to the newline-joined stdout lines, in order;
* ``stderr`` equal to the newline-joined stderr lines, in order; and
* ``exit_code`` equal to the emitted exit code, returned unchanged.

**Validates: Requirements 16.2**
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from core.code_executor import CodeExecutor, ExecutionResult, ScriptRequest
from core.orchestration_types import RunScope


class FakeExecutionManager:
    """Replays a scripted sequence of sandbox log entries (no host path)."""

    def __init__(self, log_entries, *, job_id="job-prop-38"):
        self._log_entries = list(log_entries)
        self._job_id = job_id
        self.torn_down = []

    def dispatch_job(self, spec, policy):
        return self._job_id

    def stream_logs(self, job_id):
        for entry in self._log_entries:
            yield entry

    def teardown(self, job_id):
        self.torn_down.append(job_id)


def _run_scope():
    return RunScope(run_id="run-prop-38", definition_id="def-prop-38")


# A line of captured output. Excludes newlines so each generated element maps to
# exactly one log line; the executor joins lines with "\n" on readback.
_output_line = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\n\r"),
    max_size=24,
)

# A single (stream, line) emission on stdout or stderr, interleaved arbitrarily.
_stream_entry = st.tuples(
    st.sampled_from((CodeExecutor.STDOUT_STREAM, CodeExecutor.STDERR_STREAM)),
    _output_line,
)


@settings(max_examples=200)
@given(
    entries=st.lists(_stream_entry, max_size=40),
    exit_code=st.integers(min_value=-256, max_value=256),
)
def test_captured_output_is_returned_unchanged(entries, exit_code) -> None:
    """stdout/stderr/exit_code are reconstructed from the stream unchanged."""
    # Build the sandbox log stream: interleaved stdout/stderr lines followed by
    # the terminal exit control line the runner emits on exit.
    log_entries = [{"stream": stream, "line": line} for stream, line in entries]
    log_entries.append({"stream": CodeExecutor.EXIT_STREAM, "line": str(exit_code)})

    # Expected reconstruction: lines grouped by stream, in arrival order.
    expected_stdout = "\n".join(
        line for stream, line in entries if stream == CodeExecutor.STDOUT_STREAM
    )
    expected_stderr = "\n".join(
        line for stream, line in entries if stream == CodeExecutor.STDERR_STREAM
    )

    manager = FakeExecutionManager(log_entries)
    # Constant clock keeps the timeout path inert so we only exercise capture.
    executor = CodeExecutor(manager, clock=lambda: 0.0)

    result = executor.execute(ScriptRequest(command=["./run"]), _run_scope())

    assert isinstance(result, ExecutionResult)
    assert result.timed_out is False
    assert result.stdout == expected_stdout
    assert result.stderr == expected_stderr
    assert result.exit_code == exit_code
    assert manager.torn_down == []
