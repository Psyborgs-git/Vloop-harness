"""Sandboxed code execution for agent-authored scripts.

Provides :class:`CodeExecutor`, the Control_Plane subsystem that submits
agent-authored scripts to a **Kernel-managed Sandbox** and returns the
captured result. Code is *never* executed on the host: the only execution path
is :class:`adapters.rust_infra.RustInfraExecutionManager`, which routes the job
to a sandbox workload via the kernel ``WorkloadControl.Exec`` surface
(Req 16.1, 21.1).

Security/architecture invariants honored here:

* **Sandbox only, no host fallback.** Submission goes through the injected
  execution manager's ``dispatch_job``. If routing to a sandbox fails the
  manager raises :class:`~adapters.rust_infra.SandboxRoutingError`; this
  subsystem re-raises it and provides no alternate host branch — execution is
  blocked completely (Req 21.2).
* **Captured output passthrough.** stdout, stderr, and the exit code captured
  from the sandbox are returned to the requesting agent unchanged (Req 16.2).
* **Time limit enforcement.** When a script exceeds its configured time limit
  the subsystem requests termination of the sandbox workload (``teardown``) and
  returns a timeout error instead of a normal result (Req 16.3).
* **Least-privilege grants.** The sandbox is granted exactly the Toolset and
  secret grants configured for the enclosing Workflow_Run and nothing more
  (Req 16.4). Secret grants are carried as :class:`GrantContext` references
  (grant id + session ref); raw secret values never enter Control_Plane state.

The injected execution manager exposes a deliberately small surface
(:class:`SandboxExecutionManager`): ``dispatch_job`` returns an opaque job id,
``stream_logs`` yields the sandbox's line-oriented output, and ``teardown``
terminates the workload. Because the kernel log channel is line-oriented
(``WorkloadLogLine`` carries a ``stream`` label and a ``line``), stdout and
stderr are reconstructed from the lines labeled ``"stdout"`` / ``"stderr"`` and
the process exit code is read from the terminal control line the sandbox runner
emits on the :data:`CodeExecutor.EXIT_STREAM` channel.

A monotonic ``clock`` and the per-run ``time_limit`` are injected so the timeout
path is fully deterministic and mockable in tests.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from adapters.rust_infra import SandboxRoutingError
from core.orchestration_types import GrantContext, RunScope


class SandboxExecutionManager(Protocol):
    """The minimal kernel-backed execution surface the executor depends on.

    Structurally satisfied by
    :class:`adapters.rust_infra.RustInfraExecutionManager`. Kept narrow so the
    executor has no host-execution capability of any kind.
    """

    def dispatch_job(self, spec: Mapping[str, Any], policy: Mapping[str, Any]) -> str:
        """Route a job to a Kernel-managed Sandbox and return its job id.

        Raises :class:`SandboxRoutingError` if no sandbox can be obtained.
        """
        ...

    def stream_logs(self, job_id: str) -> Iterable[Mapping[str, Any]]:
        """Yield the sandbox's line-oriented output for ``job_id``."""
        ...

    def teardown(self, job_id: str) -> None:
        """Request termination of the sandbox workload for ``job_id``."""
        ...


@dataclass(slots=True, frozen=True)
class ScriptRequest:
    """An agent-authored script to run inside a Kernel-managed Sandbox.

    ``command`` is the argv to execute; ``image`` selects the sandbox base
    image. ``time_limit_seconds`` overrides the executor's default time limit
    for this submission (``None`` falls back to the executor default).
    """

    command: Sequence[str]
    image: str = ""
    environment: Mapping[str, str] = field(default_factory=dict)
    time_limit_seconds: float | None = None
    sandbox_class: str = "worker"


@dataclass(slots=True, frozen=True)
class ExecutionResult:
    """The captured outcome of a sandboxed script execution.

    ``stdout``/``stderr``/``exit_code`` are returned unchanged from the sandbox
    (Req 16.2). On a timeout the workload was torn down, ``timed_out`` is
    ``True``, ``exit_code`` is ``None``, and ``error_message`` states the cause
    (Req 16.3); ``stdout``/``stderr`` then hold whatever was captured before
    termination.
    """

    job_id: str
    stdout: str
    stderr: str
    exit_code: int | None
    timed_out: bool = False
    error_message: str | None = None

    @property
    def ok(self) -> bool:
        """True when the script ran to completion with a zero exit code."""
        return not self.timed_out and self.exit_code == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "error_message": self.error_message,
        }


class CodeExecutor:
    """Submit agent scripts to a Kernel-managed Sandbox and capture results."""

    #: Log-stream labels used by the kernel sandbox runner.
    STDOUT_STREAM = "stdout"
    STDERR_STREAM = "stderr"
    #: Terminal control line carrying the workload's integer exit code. The
    #: sandbox runner emits a single line on this channel when the process
    #: exits; its ``line`` is the decimal exit code.
    EXIT_STREAM = "exit"

    #: Default per-run wall-clock limit (seconds) applied when neither the run
    #: nor the request specifies one.
    DEFAULT_TIME_LIMIT_SECONDS = 300.0

    def __init__(
        self,
        execution_manager: SandboxExecutionManager,
        *,
        clock: Callable[[], float] | None = None,
        default_time_limit_seconds: float | None = None,
    ) -> None:
        if execution_manager is None:
            raise ValueError("an execution manager is required; there is no host path")
        self._manager = execution_manager
        # Injected monotonic clock keeps the timeout path deterministic/mockable.
        self._clock = clock if clock is not None else time.monotonic
        self._default_time_limit = (
            default_time_limit_seconds
            if default_time_limit_seconds is not None
            else self.DEFAULT_TIME_LIMIT_SECONDS
        )

    def execute(
        self,
        request: ScriptRequest,
        run_scope: RunScope,
        *,
        toolsets: Sequence[str] | None = None,
        secret_grants: Sequence[GrantContext] | None = None,
    ) -> ExecutionResult:
        """Run ``request`` in a Sandbox scoped to ``run_scope`` and return the result.

        Builds the sandbox ``spec`` and a ``policy`` that grants the workload
        *only* the run's configured ``toolsets`` and ``secret_grants`` and
        nothing more (Req 16.4), then dispatches to a Kernel-managed Sandbox.
        Routing failures propagate as :class:`SandboxRoutingError` with no host
        fallback (Req 16.1, 21.1, 21.2). Output is captured and returned
        unchanged (Req 16.2); a time-limit breach tears the workload down and
        returns a timeout error (Req 16.3).
        """
        time_limit = self._resolve_time_limit(request)
        spec = self._build_spec(request, run_scope, time_limit)
        policy = self._build_policy(run_scope, toolsets, secret_grants, time_limit)

        # Sole execution path: route to a Kernel-managed Sandbox. A routing
        # failure blocks execution entirely — there is no host fallback branch.
        job_id = self._manager.dispatch_job(spec, policy)
        if not job_id:
            raise SandboxRoutingError(
                "sandbox dispatch returned no job id; execution blocked with "
                "no host fallback"
            )

        return self._capture(job_id, time_limit)

    # -- internals -----------------------------------------------------------

    def _resolve_time_limit(self, request: ScriptRequest) -> float:
        limit = request.time_limit_seconds
        if limit is None:
            limit = self._default_time_limit
        if limit <= 0:
            raise ValueError("time_limit_seconds must be positive")
        return float(limit)

    def _build_spec(
        self, request: ScriptRequest, run_scope: RunScope, time_limit: float
    ) -> dict[str, Any]:
        return {
            "command": list(request.command),
            "image": request.image,
            "environment": dict(request.environment),
            "class": request.sandbox_class,
            "workflow_id": run_scope.run_id,
            # Pass the limit to the kernel so it enforces a hard ceiling in
            # addition to the executor's cooperative check below.
            "timeout_seconds": int(time_limit),
        }

    def _build_policy(
        self,
        run_scope: RunScope,
        toolsets: Sequence[str] | None,
        secret_grants: Sequence[GrantContext] | None,
        time_limit: float,
    ) -> dict[str, Any]:
        # The sandbox receives exactly the run's configured toolset and grants
        # and nothing more (Req 16.4). Grants are opaque references — no raw
        # secret values cross into Control_Plane state.
        return {
            "run_id": run_scope.run_id,
            "workflow_id": run_scope.run_id,
            "definition_id": run_scope.definition_id,
            "timeout_seconds": int(time_limit),
            "toolsets": list(toolsets or ()),
            "secret_grants": [grant.to_dict() for grant in (secret_grants or ())],
        }

    def _capture(self, job_id: str, time_limit: float) -> ExecutionResult:
        """Drain the sandbox log channel, enforcing the time limit.

        stdout/stderr are accumulated from their labeled lines and returned
        unchanged; the exit code is read from the terminal control line. If the
        elapsed time exceeds ``time_limit`` the workload is torn down and a
        timeout result is returned (Req 16.3).
        """
        start = self._clock()
        deadline = start + time_limit
        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        exit_code: int | None = None

        for entry in self._manager.stream_logs(job_id):
            if self._clock() > deadline:
                return self._timeout(job_id, stdout_lines, stderr_lines, time_limit)

            stream = str(entry.get("stream", ""))
            line = entry.get("line", "")
            if stream == self.STDOUT_STREAM:
                stdout_lines.append(str(line))
            elif stream == self.STDERR_STREAM:
                stderr_lines.append(str(line))
            elif stream == self.EXIT_STREAM:
                exit_code = self._parse_exit_code(line)
            # Unrecognized streams are ignored: the executor only surfaces the
            # captured stdout/stderr/exit code, nothing it cannot attribute.

        # A breach detected only after the stream drained still terminates the
        # workload and reports a timeout.
        if self._clock() > deadline:
            return self._timeout(job_id, stdout_lines, stderr_lines, time_limit)

        return ExecutionResult(
            job_id=job_id,
            stdout="\n".join(stdout_lines),
            stderr="\n".join(stderr_lines),
            exit_code=exit_code,
        )

    def _timeout(
        self,
        job_id: str,
        stdout_lines: list[str],
        stderr_lines: list[str],
        time_limit: float,
    ) -> ExecutionResult:
        # Request termination of the sandbox workload (Req 16.3).
        self._manager.teardown(job_id)
        return ExecutionResult(
            job_id=job_id,
            stdout="\n".join(stdout_lines),
            stderr="\n".join(stderr_lines),
            exit_code=None,
            timed_out=True,
            error_message=(
                f"script exceeded the {time_limit:g}s execution time limit; "
                "the sandbox workload was terminated"
            ),
        )

    @staticmethod
    def _parse_exit_code(line: Any) -> int | None:
        try:
            return int(str(line).strip())
        except (TypeError, ValueError):
            return None
