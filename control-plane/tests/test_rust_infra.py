"""Unit tests for adapters.rust_infra.RustInfraExecutionManager (task 7.4).

These tests drive the kernel-backed execution manager through a fake gRPC stub
that records every call and returns scripted fake ``*_pb2`` responses. They
verify that:

* ``dispatch_job`` calls ``WorkloadControl.Exec`` and returns the job id.
* ``teardown`` calls ``WorkloadControl.StopWorkload``.
* ``snapshot_workspace`` calls ``FilesystemControl.Snapshot`` and returns the
  opaque snapshot reference.
* ``restore_workspace`` calls ``FilesystemControl.Restore``.
* ``request_secret_grant`` calls ``SecretControl.Grant`` and returns a
  ``GrantContext`` carrying ONLY the grant id + session reference — no raw
  secret value is ever retained (Req 16.4, 18.4).
* A sandbox-routing failure raises ``SandboxRoutingError`` with NO host
  fallback branch, and a missing grant reference raises rather than falling
  back to a raw secret (Req 21.2, 18.5).

The fake pb2 module and stub are intentionally minimal and synchronous so the
adapter is exercised without any gRPC transport (no ``run_sync`` bridge).

Requirements: 16.3, 21.2.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from adapters.rust_infra import RustInfraExecutionManager, SandboxRoutingError
from core.orchestration_types import GrantContext


# -- fake pb2 module --------------------------------------------------------


class _FakeMessage:
    """A minimal proto-message stand-in that stores constructor kwargs.

    Supports ``setattr`` (the adapter assigns the reserved ``class`` field via
    ``setattr``) and equality-by-attribute for convenient assertions.
    """

    def __init__(self, **fields):
        for key, value in fields.items():
            setattr(self, key, value)


class _FakeRequest(_FakeMessage):
    pass


def _make_fake_pb2():
    """Build a fake ``kernel_pb2``-like module exposing the request factories
    and the WorkloadClass enum constant the adapter touches."""

    return SimpleNamespace(
        WorkloadSpec=_FakeRequest,
        ExecWorkloadRequest=_FakeRequest,
        WatchWorkloadLogsRequest=_FakeRequest,
        StopWorkloadRequest=_FakeRequest,
        SnapshotWorkspaceRequest=_FakeRequest,
        RestoreWorkspaceRequest=_FakeRequest,
        GrantSecretRequest=_FakeRequest,
        # WorkloadClass enum values resolved via getattr by the adapter.
        WORKLOAD_CLASS_WORKER=2,
        WORKLOAD_CLASS_HARNESS=1,
    )


# -- fake gRPC stub ---------------------------------------------------------


class RecordingStub:
    """A fake combined gRPC stub recording every RPC call.

    Each RPC name maps to a scripted response (or a callable raising an error).
    Calls are appended to ``self.calls`` as ``(rpc_name, request, kwargs)`` so
    tests can assert exactly which RPCs ran and with what request.
    """

    def __init__(self, **responses):
        self.calls: list[tuple] = []
        self._responses = responses

    def _record(self, name, request, kwargs):
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
    def Exec(self, request, **kwargs):
        return self._record("Exec", request, kwargs)

    def StopWorkload(self, request, **kwargs):
        return self._record("StopWorkload", request, kwargs)

    def WatchWorkloadLogs(self, request, **kwargs):
        return self._record("WatchWorkloadLogs", request, kwargs)

    # FilesystemControl
    def Snapshot(self, request, **kwargs):
        return self._record("Snapshot", request, kwargs)

    def Restore(self, request, **kwargs):
        return self._record("Restore", request, kwargs)

    # SecretControl
    def Grant(self, request, **kwargs):
        return self._record("Grant", request, kwargs)


def _manager(stub):
    return RustInfraExecutionManager(stub, _make_fake_pb2())


# -- dispatch_job -----------------------------------------------------------


def test_dispatch_job_calls_exec_and_returns_job_id():
    stub = RecordingStub(Exec=SimpleNamespace(job_id="job-42", workload=None))
    manager = _manager(stub)

    job_id = manager.dispatch_job(
        {"image": "py:3.12", "command": ["python", "s.py"]},
        {"run_id": "run-1"},
    )

    assert job_id == "job-42"
    # Exactly one RPC ran, and it was Exec (sandbox routing) — no other path.
    assert stub.rpc_names == ["Exec"]
    _name, request, _kwargs = stub.calls[0]
    assert request.spec.image == "py:3.12"
    assert request.spec.command == ["python", "s.py"]
    assert request.workflow_id == "run-1"


def test_dispatch_job_uses_workload_record_id_when_job_id_absent():
    stub = RecordingStub(
        Exec=SimpleNamespace(job_id="", workload=SimpleNamespace(workload_id="wl-9"))
    )
    manager = _manager(stub)

    assert manager.dispatch_job({"command": ["x"]}, {}) == "wl-9"


# -- teardown ---------------------------------------------------------------


def test_teardown_calls_stop_workload():
    stub = RecordingStub(StopWorkload=SimpleNamespace(workload=None))
    manager = _manager(stub)

    manager.teardown("job-42")

    assert stub.rpc_names == ["StopWorkload"]
    _name, request, _kwargs = stub.calls[0]
    assert request.workload_id == "job-42"


def test_teardown_requires_job_id():
    stub = RecordingStub()
    with pytest.raises(ValueError):
        _manager(stub).teardown("")
    assert stub.calls == []


# -- snapshot_workspace -----------------------------------------------------


def test_snapshot_workspace_calls_snapshot_and_returns_ref():
    stub = RecordingStub(Snapshot=SimpleNamespace(snapshot_ref="snap-7"))
    manager = _manager(stub)

    snapshot_ref = manager.snapshot_workspace("ws-1")

    assert snapshot_ref == "snap-7"
    assert stub.rpc_names == ["Snapshot"]
    _name, request, _kwargs = stub.calls[0]
    assert request.workspace_id == "ws-1"


def test_snapshot_workspace_raises_when_no_ref_returned():
    stub = RecordingStub(Snapshot=SimpleNamespace(snapshot_ref=""))
    manager = _manager(stub)

    with pytest.raises(RuntimeError):
        manager.snapshot_workspace("ws-1")


# -- restore_workspace ------------------------------------------------------


def test_restore_workspace_calls_restore_with_snapshot_ref():
    stub = RecordingStub(Restore=SimpleNamespace(restored=True))
    manager = _manager(stub)

    manager.restore_workspace("ws-1", "snap-7")

    assert stub.rpc_names == ["Restore"]
    _name, request, _kwargs = stub.calls[0]
    assert request.workspace_id == "ws-1"
    assert request.snapshot_ref == "snap-7"


def test_restore_workspace_requires_snapshot_ref():
    stub = RecordingStub()
    with pytest.raises(ValueError):
        _manager(stub).restore_workspace("ws-1", "")
    assert stub.calls == []


# -- request_secret_grant ---------------------------------------------------


def test_request_secret_grant_calls_grant_and_returns_reference_only():
    stub = RecordingStub(
        Grant=SimpleNamespace(grant_id="g-1", session_ref="s-1")
    )
    manager = _manager(stub)

    grant = manager.request_secret_grant("secret://db", "target-pod")

    assert isinstance(grant, GrantContext)
    assert grant.grant_id == "g-1"
    assert grant.session_ref == "s-1"
    assert stub.rpc_names == ["Grant"]
    _name, request, _kwargs = stub.calls[0]
    assert request.secret_ref == "secret://db"
    assert request.target == "target-pod"


def test_grant_context_retains_no_raw_secret_value():
    """The returned context must carry ONLY grant_id + session_ref; it must
    never expose a raw secret value attribute (Req 16.4, 18.4)."""
    raw_secret = "super-secret-password"  # noqa: S105 - test literal
    stub = RecordingStub(
        # Even if the kernel response carried extra fields, the adapter must
        # only read grant_id/session_ref into Control_Plane state.
        Grant=SimpleNamespace(
            grant_id="g-1", session_ref="s-1", secret_value=raw_secret
        )
    )
    manager = _manager(stub)

    grant = manager.request_secret_grant("secret://db", "target-pod")

    # GrantContext is a slotted dataclass exposing exactly two fields.
    assert set(GrantContext.__slots__) == {"grant_id", "session_ref"}
    # No attribute holds (or can hold) a raw secret value.
    assert not hasattr(grant, "secret_value")
    assert not hasattr(grant, "secret")
    assert not hasattr(grant, "value")
    # The raw secret never appears anywhere in the context's serialized form.
    assert raw_secret not in repr(grant)
    assert raw_secret not in str(grant.to_dict())


def test_request_secret_grant_raises_when_grant_ref_missing():
    """A missing grant/session reference must raise, never fall back to a raw
    secret value (Req 18.5)."""
    stub = RecordingStub(Grant=SimpleNamespace(grant_id="", session_ref=""))
    manager = _manager(stub)

    with pytest.raises(RuntimeError):
        manager.request_secret_grant("secret://db", "target-pod")


def test_request_secret_grant_raises_when_only_session_ref_missing():
    stub = RecordingStub(Grant=SimpleNamespace(grant_id="g-1", session_ref=""))
    manager = _manager(stub)

    with pytest.raises(RuntimeError):
        manager.request_secret_grant("secret://db", "target-pod")


# -- sandbox routing failure: no host fallback (Req 21.2) -------------------


def test_exec_rpc_failure_raises_sandbox_routing_error_with_no_host_fallback():
    stub = RecordingStub(Exec=ConnectionError("kernel unreachable"))
    manager = _manager(stub)

    with pytest.raises(SandboxRoutingError):
        manager.dispatch_job({"command": ["x"]}, {})

    # Only the sandbox Exec attempt ran; no alternate/host RPC was invoked.
    assert stub.rpc_names == ["Exec"]


def test_empty_job_id_raises_sandbox_routing_error_with_no_host_fallback():
    stub = RecordingStub(Exec=SimpleNamespace(job_id="", workload=None))
    manager = _manager(stub)

    with pytest.raises(SandboxRoutingError):
        manager.dispatch_job({"command": ["x"]}, {})

    # The adapter blocked execution; it did not retry on any host path.
    assert stub.rpc_names == ["Exec"]


def test_constructor_requires_stub_and_pb2():
    with pytest.raises(ValueError):
        RustInfraExecutionManager(None, _make_fake_pb2())
    with pytest.raises(ValueError):
        RustInfraExecutionManager(RecordingStub(), None)
