"""Production execution manager backed by Rust kernel IPC.

`RustInfraExecutionManager` is the single kernel-backed execution chokepoint for
the Control_Plane. Every job is dispatched into a Kernel-managed Sandbox via the
``WorkloadControl`` gRPC surface; there is intentionally **no host execution
path**. If sandbox routing fails the dispatch is blocked and an error is raised
rather than falling back to the host (Req 21.1, 21.2).

The manager is decoupled from the gRPC transport: it talks to a
``WorkloadControl`` stub and the generated ``kernel_pb2`` module. Because the
production stub is a ``grpc.aio`` (async) stub while this interface is
synchronous, an optional ``run_sync`` bridge runs returned awaitables to
completion on the Control_Plane event loop. Tests inject a plain synchronous
stub and omit the bridge.

Workspace snapshot/restore for checkpoints is served by a ``FilesystemControl``
stub (``Snapshot``/``Restore``). It is injected separately and duck-typed; when
omitted the ``WorkloadControl`` stub is reused, so a single combined stub may
provide every RPC. The Control_Plane keeps only the opaque snapshot reference
returned by the Kernel and never the snapshot's file contents (Req 13.4).

Secret consumption is served by a ``SecretControl`` stub (``Grant``/``Revoke``),
injected separately and duck-typed in the same way (defaulting to the
``WorkloadControl`` stub when omitted). The Kernel owns raw secret values and
injects them into trusted runtime paths; ``request_secret_grant`` returns a
``GrantContext`` carrying only the grant id and an opaque session reference —
never a raw secret value (Req 6.5, 16.4, 18.4). If no grant can be issued the
call fails rather than falling back to a raw secret (Req 18.5).
"""

from __future__ import annotations

import inspect
from typing import Any, Callable, Dict, Iterator, Optional

from core.orchestration_types import GrantContext
from core.ports import IExecutionManager


class SandboxRoutingError(RuntimeError):
    """Raised when a job cannot be routed to a Kernel-managed Sandbox.

    Signals that execution was blocked with no host fallback (Req 21.2).
    """


# Map proto WorkloadClass names to enum values lazily via getattr so the adapter
# stays tolerant of stub/proto evolution.
_DEFAULT_WORKLOAD_CLASS = "WORKLOAD_CLASS_WORKER"


class RustInfraExecutionManager(IExecutionManager):
    """Dispatch, observe, and tear down sandboxed jobs against the kernel."""

    def __init__(
        self,
        stub: Any,
        pb2: Any,
        *,
        fs_stub: Optional[Any] = None,
        secret_stub: Optional[Any] = None,
        run_sync: Optional[Callable[[Any], Any]] = None,
        metadata_provider: Optional[Callable[[], Any]] = None,
        rpc_timeout: Optional[float] = None,
    ) -> None:
        if stub is None:
            raise ValueError("a WorkloadControl stub is required")
        if pb2 is None:
            raise ValueError("the kernel_pb2 module is required")
        self._stub = stub
        self._pb2 = pb2
        # FilesystemControl is injected separately and duck-typed. When omitted
        # the WorkloadControl stub is reused so a single combined stub can serve
        # every RPC.
        self._fs_stub = fs_stub if fs_stub is not None else stub
        # SecretControl is likewise injected separately and duck-typed; when
        # omitted the WorkloadControl stub is reused.
        self._secret_stub = secret_stub if secret_stub is not None else stub
        self._run_sync = run_sync
        self._metadata_provider = metadata_provider
        self._rpc_timeout = rpc_timeout

    # -- IExecutionManager ---------------------------------------------------

    def dispatch_job(self, spec: Dict[str, Any], policy: Dict[str, Any]) -> str:
        """Dispatch a job into a Kernel-managed Sandbox and return its job id.

        Routing always targets a sandbox (``WorkloadControl.Exec``). Any failure
        to obtain or reach the sandbox blocks execution and raises
        ``SandboxRoutingError`` — there is no host fallback (Req 21.1, 21.2).
        """
        spec = spec or {}
        policy = policy or {}
        request = self._build_exec_request(spec, policy)
        try:
            response = self._call(self._stub.Exec, request)
        except SandboxRoutingError:
            raise
        except Exception as exc:  # noqa: BLE001 - re-raised as routing failure
            raise SandboxRoutingError(
                "failed to route job to a kernel-managed sandbox; "
                "execution blocked with no host fallback"
            ) from exc

        job_id = self._extract_job_id(response)
        if not job_id:
            raise SandboxRoutingError(
                "kernel sandbox exec returned no job identifier; "
                "execution blocked with no host fallback"
            )
        return job_id

    def stream_logs(self, job_id: str) -> Iterator[Dict[str, Any]]:
        """Yield captured stdout/stderr log lines for a dispatched job."""
        if not job_id:
            raise ValueError("job_id is required to stream logs")
        request = self._pb2.WatchWorkloadLogsRequest(workload_id=job_id)
        stream = self._call(self._stub.WatchWorkloadLogs, request)
        for line in self._iterate(stream):
            yield {
                "stream": getattr(line, "stream", ""),
                "line": getattr(line, "line", ""),
                "timestampUnixMs": getattr(line, "timestamp_unix_ms", 0),
            }

    def teardown(self, job_id: str) -> None:
        """Request teardown of an in-flight sandbox workload for a job."""
        if not job_id:
            raise ValueError("job_id is required to tear down a job")
        request = self._pb2.StopWorkloadRequest(workload_id=job_id)
        self._call(self._stub.StopWorkload, request)

    # -- workspace snapshot / restore ---------------------------------------

    def snapshot_workspace(self, workspace_id: str) -> str:
        """Snapshot a sandbox workspace and return the Kernel snapshot reference.

        Calls ``FilesystemControl.Snapshot``. The Kernel owns and persists the
        snapshot contents; the Control_Plane retains only the returned opaque
        reference, never the file contents themselves (Req 13.1, 13.4).
        """
        if not workspace_id:
            raise ValueError("workspace_id is required to snapshot a workspace")
        request = self._pb2.SnapshotWorkspaceRequest(workspace_id=workspace_id)
        response = self._call(self._fs_stub.Snapshot, request)
        snapshot_ref = self._extract_snapshot_ref(response)
        if not snapshot_ref:
            raise RuntimeError(
                "kernel snapshot returned no snapshot reference for "
                f"workspace {workspace_id!r}"
            )
        return snapshot_ref

    def restore_workspace(self, workspace_id: str, snap: str) -> None:
        """Restore a sandbox workspace to a previously captured snapshot.

        Calls ``FilesystemControl.Restore`` with the opaque Kernel-owned
        snapshot reference; the Kernel performs the actual restore (Req 13.2).
        """
        if not workspace_id:
            raise ValueError("workspace_id is required to restore a workspace")
        if not snap:
            raise ValueError("a snapshot reference is required to restore a workspace")
        request = self._pb2.RestoreWorkspaceRequest(
            workspace_id=workspace_id,
            snapshot_ref=snap,
        )
        self._call(self._fs_stub.Restore, request)

    # -- secret grants -------------------------------------------------------

    def request_secret_grant(self, secret_ref: str, target: str) -> GrantContext:
        """Request a Kernel secret grant for a target and return its reference.

        Calls ``SecretControl.Grant``. The Kernel owns the raw secret value and
        injects it into the target's trusted runtime path; the Control_Plane
        receives only the grant id and an opaque session reference and never a
        raw secret value (Req 6.5, 16.4, 18.4). If no grant can be issued the
        call fails rather than falling back to a raw secret value (Req 18.5).
        """
        if not secret_ref:
            raise ValueError("a secret reference is required to request a grant")
        if not target:
            raise ValueError("a grant target is required to request a grant")
        request = self._pb2.GrantSecretRequest(
            secret_ref=secret_ref,
            target=target,
        )
        response = self._call(self._secret_stub.Grant, request)
        grant_id = self._extract_grant_id(response)
        session_ref = self._extract_session_ref(response)
        if not grant_id or not session_ref:
            raise RuntimeError(
                "kernel secret grant returned no grant reference for secret "
                f"{secret_ref!r}; no raw-secret fallback is permitted"
            )
        # GrantContext carries only the grant id and session reference; a raw
        # secret value is never read into Control_Plane state (Req 6.5, 18.4).
        return GrantContext(grant_id=grant_id, session_ref=session_ref)

    # -- internals -----------------------------------------------------------

    def _build_exec_request(
        self, spec: Dict[str, Any], policy: Dict[str, Any]
    ) -> Any:
        command = spec.get("command", [])
        if isinstance(command, str):
            command = [command]
        elif command is None:
            command = []
        else:
            command = list(command)

        environment = dict(spec.get("environment", {}) or {})
        ports = list(spec.get("ports", []) or [])

        workload_spec = self._pb2.WorkloadSpec(
            image=spec.get("image", "") or "",
            command=command,
            ports=ports,
            environment=environment,
        )
        # Sandbox class: command/file-mutating jobs run as worker sandboxes
        # unless the caller pins a specific class. Set via setattr because
        # `class` is a reserved word in Python.
        class_name = str(spec.get("class", _DEFAULT_WORKLOAD_CLASS)).upper()
        if not class_name.startswith("WORKLOAD_CLASS_"):
            class_name = f"WORKLOAD_CLASS_{class_name}"
        class_enum = getattr(
            self._pb2,
            class_name,
            getattr(self._pb2, _DEFAULT_WORKLOAD_CLASS),
        )
        setattr(workload_spec, "class", class_enum)

        workflow_id = str(
            spec.get("workflow_id")
            or policy.get("workflow_id")
            or policy.get("run_id")
            or ""
        )
        timeout_seconds = int(
            spec.get("timeout_seconds")
            or policy.get("timeout_seconds")
            or 0
        )

        return self._pb2.ExecWorkloadRequest(
            spec=workload_spec,
            workflow_id=workflow_id,
            timeout_seconds=timeout_seconds,
        )

    @staticmethod
    def _extract_job_id(response: Any) -> str:
        if response is None:
            return ""
        job_id = getattr(response, "job_id", "") or ""
        if job_id:
            return job_id
        workload = getattr(response, "workload", None)
        if workload is not None:
            return getattr(workload, "workload_id", "") or ""
        return ""

    @staticmethod
    def _extract_snapshot_ref(response: Any) -> str:
        if response is None:
            return ""
        return getattr(response, "snapshot_ref", "") or ""

    @staticmethod
    def _extract_grant_id(response: Any) -> str:
        if response is None:
            return ""
        return getattr(response, "grant_id", "") or ""

    @staticmethod
    def _extract_session_ref(response: Any) -> str:
        if response is None:
            return ""
        return getattr(response, "session_ref", "") or ""

    def _call(self, method: Callable[..., Any], request: Any) -> Any:
        """Invoke a unary gRPC method, resolving awaitables when bridged."""
        kwargs: Dict[str, Any] = {}
        metadata = self._metadata()
        if metadata is not None:
            kwargs["metadata"] = metadata
        if self._rpc_timeout is not None:
            kwargs["timeout"] = self._rpc_timeout
        result = method(request, **kwargs)
        return self._resolve(result)

    def _resolve(self, result: Any) -> Any:
        if inspect.isawaitable(result):
            if self._run_sync is None:
                raise RuntimeError(
                    "kernel stub returned an awaitable but no run_sync bridge "
                    "was provided"
                )
            return self._run_sync(result)
        return result

    def _iterate(self, stream: Any) -> Iterator[Any]:
        """Iterate a unary-stream response, draining async streams via the bridge."""
        if hasattr(stream, "__aiter__"):
            if self._run_sync is None:
                raise RuntimeError(
                    "kernel stub returned an async stream but no run_sync bridge "
                    "was provided"
                )
            return iter(self._run_sync(_drain_async_stream(stream)))
        return iter(stream)

    def _metadata(self) -> Any:
        if self._metadata_provider is None:
            return None
        return self._metadata_provider()


async def _drain_async_stream(stream: Any) -> list:
    items = []
    async for item in stream:
        items.append(item)
    return items
