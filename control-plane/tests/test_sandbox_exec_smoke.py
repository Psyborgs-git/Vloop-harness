"""Integration smoke test for the kernel-backed sandbox exec path (task 32.1).

This test exercises a full sandbox exec round-trip through
``adapters.rust_infra.RustInfraExecutionManager`` end-to-end, against a MOCKED
kernel gRPC surface — no live kernel is required. Unlike the focused unit tests
in ``tests/test_rust_infra.py`` (which drive a synchronous fake stub), this
smoke test wires the manager the way the production runtime does in
``cp/runtime.py::_wire_execution_manager``:

* the kernel stub methods are ``async`` (mirroring the real ``grpc.aio`` stub),
* awaitables are resolved through a ``run_sync`` bridge that runs the coroutine
  to completion on a background event loop via ``run_coroutine_threadsafe``
  (mirroring ``VloopRuntime._run_on_loop``),
* a ``metadata_provider`` supplies per-call session metadata, and
* the manager is built against the REAL generated ``kernel_pb2`` messages
  loaded via ``core.generated.load_kernel_modules`` so the spec/policy →
  proto-field mapping and the response extraction are integration-exercised.

Coverage:
* ``dispatch_job`` maps spec/policy onto the ``ExecWorkloadRequest`` proto and
  returns the kernel-issued job id (Req 16.1 sandbox exec, Req 16.2 result
  passthrough by returning the job id used for log streaming).
* ``snapshot_workspace`` / ``restore_workspace`` round-trip the FS snapshot
  reference through ``FilesystemControl`` (Req 16.1 sandbox FS path; the
  snapshot/restore surface backing checkpoints).
* NO-HOST-FALLBACK boundary: when kernel routing is unavailable the manager
  raises ``SandboxRoutingError`` and never reaches an alternate/host path, and
  the adapter module contains no host-execution primitives at all (Req 21.1).

Requirements: 16.1, 16.2, 21.1.
"""

from __future__ import annotations

import asyncio
import inspect
import threading
from pathlib import Path

import pytest

from adapters.rust_infra import RustInfraExecutionManager, SandboxRoutingError
from core.generated import load_kernel_modules
from core.orchestration_types import GrantContext


# ---------------------------------------------------------------------------
# Real generated kernel_pb2 (integration surface)
# ---------------------------------------------------------------------------

# Loading the real generated messages exercises the actual proto field mapping
# rather than a hand-rolled fake. Skip cleanly if stub generation is impossible
# in this environment (e.g. grpcio-tools missing) so the smoke test never
# produces a false negative for unrelated reasons.
try:
    KERNEL_PB2, _KERNEL_PB2_GRPC = load_kernel_modules()
except Exception as exc:  # pragma: no cover - environment dependent
    pytest.skip(
        f"kernel gRPC stubs unavailable: {exc}", allow_module_level=True
    )


# ---------------------------------------------------------------------------
# run_sync bridge — mirrors VloopRuntime._run_on_loop
# ---------------------------------------------------------------------------


class _BackgroundLoop:
    """A background asyncio loop with a synchronous ``run_sync`` bridge.

    The production runtime resolves awaitables returned by the async ``grpc.aio``
    stub by scheduling them on the Control_Plane event loop from worker threads
    (``asyncio.run_coroutine_threadsafe(...).result()``). This helper reproduces
    that exact bridge so the smoke test drives the same awaitable-resolution
    path the adapter uses in production.
    """

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def run_sync(self, coro):
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=5)

    def close(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)
        self._loop.close()


@pytest.fixture()
def bridge():
    loop = _BackgroundLoop()
    try:
        yield loop
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Mocked async kernel stub
# ---------------------------------------------------------------------------


class AsyncKernelStub:
    """A fake combined async kernel stub covering Workload/Filesystem/Secret RPCs.

    Every method is a coroutine (like the real ``grpc.aio`` stub) so the adapter
    must route it through the ``run_sync`` bridge. Each call is recorded as
    ``(rpc_name, request, kwargs)`` and returns a canned real-proto response, or
    raises the scripted error when one is configured (to model kernel routing
    being unavailable).
    """

    def __init__(self, **responses) -> None:
        self.calls: list[tuple] = []
        self._responses = responses

    async def _record(self, name, request, kwargs):
        self.calls.append((name, request, kwargs))
        response = self._responses.get(name)
        if isinstance(response, Exception):
            raise response
        if callable(response):
            return response(request)
        return response

    @property
    def rpc_names(self) -> list[str]:
        return [name for name, _req, _kw in self.calls]

    # WorkloadControl
    async def Exec(self, request, **kwargs):
        return await self._record("Exec", request, kwargs)

    async def StopWorkload(self, request, **kwargs):
        return await self._record("StopWorkload", request, kwargs)

    # FilesystemControl
    async def Snapshot(self, request, **kwargs):
        return await self._record("Snapshot", request, kwargs)

    async def Restore(self, request, **kwargs):
        return await self._record("Restore", request, kwargs)

    # SecretControl
    async def Grant(self, request, **kwargs):
        return await self._record("Grant", request, kwargs)


_SESSION_METADATA = [("x-vloop-session-id", "sess-smoke-1")]


def _manager(stub, bridge) -> RustInfraExecutionManager:
    """Wire the manager exactly as cp/runtime.py does: async stub + run_sync
    bridge + metadata provider + rpc timeout, over the real kernel_pb2."""
    return RustInfraExecutionManager(
        stub,
        KERNEL_PB2,
        run_sync=bridge.run_sync,
        metadata_provider=lambda: _SESSION_METADATA,
        rpc_timeout=5.0,
    )


# ---------------------------------------------------------------------------
# Sanity: the mocked stub really is async (proves the bridge is exercised)
# ---------------------------------------------------------------------------


def test_mock_stub_methods_are_coroutines():
    stub = AsyncKernelStub()
    assert inspect.iscoroutinefunction(stub.Exec)
    assert inspect.iscoroutinefunction(stub.Snapshot)
    assert inspect.iscoroutinefunction(stub.Restore)
    assert inspect.iscoroutinefunction(stub.Grant)


# ---------------------------------------------------------------------------
# dispatch_job round-trip (Req 16.1, 16.2)
# ---------------------------------------------------------------------------


def test_dispatch_job_round_trips_through_kernel_exec(bridge):
    """A sandbox exec round-trips: spec/policy map onto the ExecWorkloadRequest
    proto and the kernel-issued job id is returned."""
    stub = AsyncKernelStub(
        Exec=KERNEL_PB2.ExecWorkloadResponse(job_id="job-smoke-1")
    )
    manager = _manager(stub, bridge)

    job_id = manager.dispatch_job(
        {
            "image": "python:3.12",
            "command": ["python", "-c", "print('hi')"],
            "environment": {"MODE": "smoke"},
            "timeout_seconds": 30,
        },
        {"run_id": "run-smoke-1"},
    )

    # Round-trip returned the kernel-issued job id.
    assert job_id == "job-smoke-1"

    # Exactly one RPC ran, and it was the sandbox Exec path — the only exec path.
    assert stub.rpc_names == ["Exec"]
    name, request, kwargs = stub.calls[0]
    assert name == "Exec"

    # spec/policy were faithfully mapped onto the real ExecWorkloadRequest proto.
    assert isinstance(request, KERNEL_PB2.ExecWorkloadRequest)
    assert request.spec.image == "python:3.12"
    assert list(request.spec.command) == ["python", "-c", "print('hi')"]
    assert dict(request.spec.environment) == {"MODE": "smoke"}
    # Command/file-mutating jobs default to the WORKER sandbox class.
    assert getattr(request.spec, "class") == KERNEL_PB2.WORKLOAD_CLASS_WORKER
    assert request.workflow_id == "run-smoke-1"
    assert request.timeout_seconds == 30

    # The runtime-style wiring propagated session metadata and the rpc timeout
    # onto the underlying async call (proving the production bridge path).
    assert kwargs.get("metadata") == _SESSION_METADATA
    assert kwargs.get("timeout") == 5.0


def test_dispatch_job_returns_workload_id_when_job_id_absent(bridge):
    """When the kernel response omits job_id, the workload record id is used."""
    stub = AsyncKernelStub(
        Exec=KERNEL_PB2.ExecWorkloadResponse(
            workload=KERNEL_PB2.WorkloadRecord(workload_id="wl-smoke-2")
        )
    )
    manager = _manager(stub, bridge)

    assert manager.dispatch_job({"command": ["echo", "x"]}, {}) == "wl-smoke-2"
    assert stub.rpc_names == ["Exec"]


# ---------------------------------------------------------------------------
# snapshot / restore round-trip (Req 16.1 sandbox FS path)
# ---------------------------------------------------------------------------


def test_snapshot_workspace_returns_kernel_snapshot_ref(bridge):
    stub = AsyncKernelStub(
        Snapshot=KERNEL_PB2.SnapshotWorkspaceResponse(snapshot_ref="snap-smoke-9")
    )
    manager = _manager(stub, bridge)

    snapshot_ref = manager.snapshot_workspace("ws-smoke-1")

    assert snapshot_ref == "snap-smoke-9"
    assert stub.rpc_names == ["Snapshot"]
    _name, request, _kwargs = stub.calls[0]
    assert isinstance(request, KERNEL_PB2.SnapshotWorkspaceRequest)
    assert request.workspace_id == "ws-smoke-1"


def test_restore_workspace_issues_restore_call(bridge):
    stub = AsyncKernelStub(
        Restore=KERNEL_PB2.RestoreWorkspaceResponse(restored=True)
    )
    manager = _manager(stub, bridge)

    manager.restore_workspace("ws-smoke-1", "snap-smoke-9")

    assert stub.rpc_names == ["Restore"]
    _name, request, _kwargs = stub.calls[0]
    assert isinstance(request, KERNEL_PB2.RestoreWorkspaceRequest)
    assert request.workspace_id == "ws-smoke-1"
    assert request.snapshot_ref == "snap-smoke-9"


def test_snapshot_then_restore_round_trip(bridge):
    """The snapshot reference returned by the kernel is exactly what a
    subsequent restore replays back to the kernel."""
    stub = AsyncKernelStub(
        Snapshot=KERNEL_PB2.SnapshotWorkspaceResponse(snapshot_ref="snap-rt"),
        Restore=KERNEL_PB2.RestoreWorkspaceResponse(restored=True),
    )
    manager = _manager(stub, bridge)

    snap = manager.snapshot_workspace("ws-rt")
    manager.restore_workspace("ws-rt", snap)

    assert stub.rpc_names == ["Snapshot", "Restore"]
    _n, restore_req, _k = stub.calls[1]
    assert restore_req.snapshot_ref == snap


# ---------------------------------------------------------------------------
# Secret grant reaches the sandbox exec path by reference only (Req 16.1 path)
# ---------------------------------------------------------------------------


def test_request_secret_grant_returns_reference_only(bridge):
    stub = AsyncKernelStub(
        Grant=KERNEL_PB2.GrantSecretResponse(
            grant_id="g-smoke", session_ref="s-smoke"
        )
    )
    manager = _manager(stub, bridge)

    grant = manager.request_secret_grant("secret://provider/key", "job-smoke-1")

    assert isinstance(grant, GrantContext)
    assert grant.grant_id == "g-smoke"
    assert grant.session_ref == "s-smoke"
    assert stub.rpc_names == ["Grant"]


# ---------------------------------------------------------------------------
# NO-HOST-FALLBACK boundary (Req 21.1)
# ---------------------------------------------------------------------------


def test_kernel_unavailable_raises_sandbox_routing_error_no_host_fallback(bridge):
    """When kernel routing is unavailable, dispatch is blocked with
    SandboxRoutingError and NO alternate/host RPC is attempted."""

    class _Unavailable(RuntimeError):
        """Stand-in for a gRPC UNAVAILABLE status from a down kernel."""

    stub = AsyncKernelStub(Exec=_Unavailable("kernel channel unavailable"))
    manager = _manager(stub, bridge)

    with pytest.raises(SandboxRoutingError):
        manager.dispatch_job(
            {"command": ["python", "-c", "print(1)"]}, {"run_id": "run-x"}
        )

    # Only the sandbox Exec attempt ran — the manager did not fall back to any
    # other execution path when the kernel was unreachable.
    assert stub.rpc_names == ["Exec"]


def test_empty_job_id_blocks_execution_no_host_fallback(bridge):
    """A kernel response with no job identifier blocks execution rather than
    silently completing or running on the host."""
    stub = AsyncKernelStub(Exec=KERNEL_PB2.ExecWorkloadResponse(job_id=""))
    manager = _manager(stub, bridge)

    with pytest.raises(SandboxRoutingError):
        manager.dispatch_job({"command": ["x"]}, {})

    assert stub.rpc_names == ["Exec"]


def test_adapter_has_no_host_execution_primitives():
    """Static guarantee: the kernel adapter contains no host-execution code
    path. There is no import or use of subprocess/os.system/os.popen/os.exec*
    or eval/exec — the only execution path is the kernel gRPC Exec RPC (Req
    21.1)."""
    # Resolve the adapter source path robustly from the imported module.
    import adapters.rust_infra as _mod

    text = Path(_mod.__file__).read_text(encoding="utf-8")

    forbidden = [
        "import subprocess",
        "subprocess.",
        "os.system",
        "os.popen",
        "os.exec",
        "os.spawn",
        "pty.spawn",
        "eval(",
        "exec(",
    ]
    offenders = [token for token in forbidden if token in text]
    assert offenders == [], (
        "kernel adapter must have no host-execution path; found: " f"{offenders}"
    )
