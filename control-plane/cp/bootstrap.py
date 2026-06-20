"""Control-plane bootstrap, kernel registration, HTTP shell, and window ownership."""

from __future__ import annotations

import asyncio
import importlib
import logging
import signal
import threading
import time
import uuid
from contextlib import suppress
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from core.agent import AgentOrchestrator
from core.gateway import ProviderService
from core.generated import load_kernel_modules
from core.store import SQLiteState
from cp.config_service import ControlPlaneConfig, KernelActiveConfig, load_active_config
from cp.events import KernelEventRouter, start_event_router
from cp.http_api import HttpShellServer
from cp.window import WindowManager

LOGGER = logging.getLogger("vloop.control_plane")


@dataclass(slots=True)
class SessionSnapshot:
    status: str
    kernel_endpoint: str
    http_base_url: str | None
    shell_url: str | None
    session_id: str | None
    granted_scopes: list[str]
    last_registered_at_unix_ms: int | None
    last_heartbeat_at_unix_ms: int | None
    last_error: str | None
    active_config: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ControlPlaneRuntime:
    def __init__(
        self, config: ControlPlaneConfig, window_manager: WindowManager
    ) -> None:
        self.config = config
        self.window_manager = window_manager
        self.shutdown_event = asyncio.Event()
        self.event_router: KernelEventRouter = start_event_router(
            self.window_manager,
            max_events=config.event_buffer_size,
        )

        self.kernel_pb2, self.kernel_pb2_grpc = load_kernel_modules()
        try:
            self.grpc = importlib.import_module("grpc")
        except ModuleNotFoundError as exc:  # pragma: no cover - depends on local env
            raise RuntimeError(
                "grpcio is required for the control plane to register with the kernel. "
                "Install control-plane dependencies first."
            ) from exc

        self.state = SQLiteState(self._state_db_path())
        self.provider_service = ProviderService(self.state)
        self.agent_orchestrator = AgentOrchestrator(self.state, self.provider_service)

        self.status = "starting"
        self.session_id: str | None = None
        self.granted_scopes: list[str] = []
        self.active_config: KernelActiveConfig | None = None
        self.last_registered_at_unix_ms: int | None = None
        self.last_heartbeat_at_unix_ms: int | None = None
        self.last_error: str | None = None
        self.http_server: HttpShellServer | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._grpc_channel: Any = None
        self._workload_stub: Any = None
        self._workload_cache: dict[str, dict[str, Any]] = {}
        self._workload_logs: dict[str, list[str]] = {}

    async def run(self) -> None:
        self._loop = asyncio.get_running_loop()
        try:
            await self._start_http_shell_if_enabled()

            backoff = self.config.reconnect_backoff_seconds
            while not self.shutdown_event.is_set():
                try:
                    await self._run_kernel_session()
                    backoff = self.config.reconnect_backoff_seconds
                except Exception as exc:  # pragma: no cover - runtime path
                    if self.shutdown_event.is_set():
                        break
                    self.status = "reconnecting"
                    self.last_error = str(exc)
                    LOGGER.exception("control plane kernel session failed: %s", exc)
                    await self._sleep_or_stop(backoff)
                    backoff = min(backoff * 2, 15.0)
        finally:
            if self.http_server is not None:
                self.http_server.stop()

    def request_shutdown(self) -> None:
        if self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self.shutdown_event.set)

    async def _start_http_shell_if_enabled(self) -> None:
        if not self.config.serve_http:
            return

        self.status = "starting_http"
        self.http_server = HttpShellServer(self)
        self.http_server.start()
        self.window_manager.attach_shell_url(self.config.shell_url())
        self.status = "serving_http"
        LOGGER.info("control-plane HTTP shell ready at %s", self.config.shell_url())

    async def _run_kernel_session(self) -> None:
        self.status = "connecting"
        self.last_error = None
        channel = self.grpc.aio.insecure_channel(
            self.config.kernel_endpoint,
            options=[("grpc.default_authority", "localhost")],
        )
        self._grpc_channel = channel
        self._workload_stub = self.kernel_pb2_grpc.WorkloadControlStub(channel)
        try:
            await asyncio.wait_for(
                channel.channel_ready(),
                timeout=self.config.connect_timeout_seconds,
            )
            stub = self.kernel_pb2_grpc.KernelLifecycleStub(channel)
            response = await stub.RegisterControlPlane(
                self.kernel_pb2.RegisterControlPlaneRequest(
                    version=self.config.version,
                    capabilities=self.config.announced_capabilities,
                    metadata=self.config.registration_metadata(),
                ),
                metadata=self._metadata(include_bootstrap=True),
                timeout=self.config.rpc_timeout_seconds,
            )

            self.session_id = response.session_id
            self.granted_scopes = list(response.granted_scopes)
            self.active_config = KernelActiveConfig.from_proto(response.active_config)
            self.last_registered_at_unix_ms = _now_unix_ms()
            self.last_heartbeat_at_unix_ms = self.last_registered_at_unix_ms
            self.status = "registered"
            LOGGER.info(
                "registered with kernel session %s on %s",
                self.session_id,
                self.config.kernel_endpoint,
            )

            if self.config.open_window_on_boot:
                self.window_manager.open_main_window("control plane boot complete")

            heartbeat_task = asyncio.create_task(self._heartbeat_loop(stub))
            event_task = asyncio.create_task(self._event_loop(stub))
            shutdown_task = asyncio.create_task(self.shutdown_event.wait())

            done, pending = await asyncio.wait(
                {heartbeat_task, event_task, shutdown_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in pending:
                task.cancel()
            for task in pending:
                with suppress(asyncio.CancelledError):
                    await task

            if shutdown_task in done:
                return

            for task in done:
                if task is shutdown_task:
                    continue
                exception = task.exception()
                if exception is not None:
                    raise exception
                raise RuntimeError("control plane kernel session ended unexpectedly")
        finally:
            self.status = (
                "disconnected" if not self.shutdown_event.is_set() else "shutting_down"
            )
            self.session_id = None
            self.granted_scopes = []
            await channel.close()

    async def _heartbeat_loop(self, stub: Any) -> None:
        while not self.shutdown_event.is_set():
            await self._sleep_or_stop(self.config.heartbeat_interval_seconds)
            if self.shutdown_event.is_set() or not self.session_id:
                break

            response = await stub.ControlPlaneHeartbeat(
                self.kernel_pb2.ControlPlaneHeartbeatRequest(
                    session_id=self.session_id
                ),
                metadata=self._metadata(include_session=True),
                timeout=self.config.rpc_timeout_seconds,
            )
            self.last_heartbeat_at_unix_ms = _now_unix_ms()
            LOGGER.debug(
                "kernel heartbeat acknowledged for session %s with health %s",
                self.session_id,
                response.kernel_health,
            )

    async def _event_loop(self, stub: Any) -> None:
        if not self.session_id:
            raise RuntimeError(
                "cannot watch kernel events before registering a session"
            )

        stream = stub.WatchKernelEvents(
            self.kernel_pb2.WatchKernelEventsRequest(session_id=self.session_id),
            metadata=self._metadata(include_session=True),
        )
        async for event in stream:
            self.event_router.handle_proto_event(event)

    def health_snapshot(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "version": self.config.version,
            "kernel_endpoint": self.config.kernel_endpoint,
            "http_base_url": self.config.http_base_url()
            if self.config.serve_http
            else None,
            "shell_url": self.config.shell_url() if self.config.serve_http else None,
            "session_id": self.session_id,
            "last_error": self.last_error,
            "window": self.window_snapshot(),
        }

    def session_snapshot(self) -> dict[str, Any]:
        return SessionSnapshot(
            status=self.status,
            kernel_endpoint=self.config.kernel_endpoint,
            http_base_url=self.config.http_base_url()
            if self.config.serve_http
            else None,
            shell_url=self.config.shell_url() if self.config.serve_http else None,
            session_id=self.session_id,
            granted_scopes=list(self.granted_scopes),
            last_registered_at_unix_ms=self.last_registered_at_unix_ms,
            last_heartbeat_at_unix_ms=self.last_heartbeat_at_unix_ms,
            last_error=self.last_error,
            active_config=self.active_config.to_dict() if self.active_config else None,
        ).to_dict()

    def event_snapshot(self) -> dict[str, Any]:
        return self.event_router.snapshot()

    def window_snapshot(self) -> dict[str, Any]:
        return self.window_manager.snapshot().to_dict()

    def system_snapshot(self) -> dict[str, Any]:
        events = self.event_snapshot()
        return {
            "health": self.health_snapshot(),
            "session": self.session_snapshot(),
            "window": self.window_snapshot(),
            "dependencies": self.dependency_snapshot(),
            "recentEvents": events.get("recent_events", []),
            "eventCount": events.get("event_count", 0),
        }

    def dependency_snapshot(self) -> dict[str, Any]:
        """Fetch live dependency status from the kernel via gRPC GetDependencies."""
        try:
            return self._run_on_loop(self._dependency_snapshot_async())
        except Exception as exc:
            LOGGER.warning("failed to fetch kernel dependencies: %s", exc)
            return {"dependencies": [], "error": str(exc)}

    async def _dependency_snapshot_async(self) -> dict[str, Any]:
        if self._grpc_channel is None:
            return {"dependencies": [], "error": "gRPC channel is not connected"}
        deps_stub = self.kernel_pb2_grpc.KernelLifecycleStub(self._grpc_channel)
        response = await deps_stub.GetDependencies(
            self.kernel_pb2.GetDependenciesRequest(),
            metadata=self._metadata(include_session=True),
            timeout=self.config.rpc_timeout_seconds,
        )
        return {
            "dependencies": [
                {
                    "name": dep.name,
                    "state": self.kernel_pb2.DependencyState.Name(dep.state),
                    "message": dep.message,
                    "detectedVersion": dep.detected_version or None,
                    "remediation": dep.remediation or None,
                }
                for dep in response.dependencies
            ],
        }

    def provider_catalog(self) -> list[dict[str, Any]]:
        return self.provider_service.provider_catalog()

    def list_providers(self) -> list[dict[str, Any]]:
        return self.provider_service.list_providers()

    def get_provider(self, provider_id: str) -> dict[str, Any] | None:
        return self.provider_service.get_provider(provider_id)

    def save_provider(
        self, payload: dict[str, Any], provider_id: str | None = None
    ) -> dict[str, Any]:
        return self.provider_service.save_provider(payload, provider_id)

    def delete_provider(self, provider_id: str) -> None:
        self.provider_service.delete_provider(provider_id)

    def test_provider(self, provider_id: str) -> dict[str, Any]:
        return self.provider_service.test_provider(provider_id)

    def delete_session_secret(self, provider_id: str) -> dict[str, Any]:
        return self.provider_service.delete_session_secret(provider_id)

    def list_agent_templates(self) -> list[dict[str, Any]]:
        return self.agent_orchestrator.list_templates()

    def list_agents(self) -> list[dict[str, Any]]:
        return self.agent_orchestrator.list_agents()

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        return self.agent_orchestrator.get_agent(agent_id)

    def save_agent(
        self, payload: dict[str, Any], agent_id: str | None = None
    ) -> dict[str, Any]:
        return self.agent_orchestrator.save_agent(payload, agent_id)

    def delete_agent(self, agent_id: str) -> None:
        self.agent_orchestrator.delete_agent(agent_id)

    def validate_agent(
        self, payload: dict[str, Any], agent_id: str | None = None
    ) -> dict[str, Any]:
        return self.agent_orchestrator.validate_agent(payload, agent_id)

    def list_invocations(self, agent_id: str | None = None) -> list[dict[str, Any]]:
        return self.agent_orchestrator.list_invocations(agent_id)

    def get_invocation(self, invocation_id: str) -> dict[str, Any] | None:
        return self.agent_orchestrator.get_invocation(invocation_id)

    def get_invocation_events(self, invocation_id: str) -> list[dict[str, Any]]:
        return self.agent_orchestrator.get_invocation_events(invocation_id)

    def invoke_agent(self, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.agent_orchestrator.invoke_agent(agent_id, payload)

    def _run_on_loop(self, coro):
        """Run an async coroutine on the CP's event loop, blocking until complete.

        The HTTP server runs in daemon threads so ``asyncio.run()`` would create a
        new loop that conflicts with the aio gRPC channel.  This helper delegates
        to the loop that owns the channel.
        """
        if self._loop is None or self._loop.is_closed():
            raise RuntimeError("control-plane event loop is not available")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=self.config.rpc_timeout_seconds)

    def list_workloads(self) -> list[dict[str, Any]]:
        return self._run_on_loop(self._list_workloads_async())

    async def _list_workloads_async(self) -> list[dict[str, Any]]:
        if self._workload_stub is None:
            return []
        try:
            response = await self._workload_stub.ListWorkloads(
                self.kernel_pb2.ListWorkloadsRequest(),
                metadata=self._metadata(include_session=True),
                timeout=self.config.rpc_timeout_seconds,
            )
            workloads = [_workload_to_dict(w) for w in response.workloads]
            self._workload_cache = {w["workloadId"]: w for w in workloads}
            return workloads
        except Exception as exc:
            LOGGER.warning("failed to list workloads: %s", exc)
            return []

    def create_workload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._run_on_loop(self._create_workload_async(payload))

    async def _create_workload_async(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._workload_stub is None:
            raise RuntimeError("kernel workload stub is not connected")
        image = _required_string(payload, "image")
        command = payload.get("command", [])
        if isinstance(command, str):
            command = [command]
        ports = payload.get("ports", [])
        environment = payload.get("environment", {})
        class_name = payload.get("class", "HARNESS")
        class_enum = getattr(
            self.kernel_pb2,
            f"WORKLOAD_CLASS_{class_name.upper()}",
            self.kernel_pb2.WORKLOAD_CLASS_HARNESS,
        )

        spec = self.kernel_pb2.WorkloadSpec(
            image=image,
            command=command if isinstance(command, list) else list(command),
            ports=ports,
            environment=environment,
        )
        # `class` is a Python reserved word; set via setattr
        setattr(spec, "class", class_enum)
        req = self.kernel_pb2.CreateWorkloadRequest(spec=spec)
        response = await self._workload_stub.CreateWorkload(
            req,
            metadata=self._metadata(include_session=True),
            timeout=self.config.rpc_timeout_seconds,
        )
        workload = _workload_to_dict(response.workload)
        self._workload_cache[workload["workloadId"]] = workload
        return workload

    def get_workload(self, workload_id: str) -> dict[str, Any]:
        return self._run_on_loop(self._get_workload_async(workload_id))

    async def _get_workload_async(self, workload_id: str) -> dict[str, Any]:
        if self._workload_stub is None:
            raise RuntimeError("kernel workload stub is not connected")
        req = self.kernel_pb2.GetWorkloadRequest(workload_id=workload_id)
        response = await self._workload_stub.GetWorkload(
            req,
            metadata=self._metadata(include_session=True),
            timeout=self.config.rpc_timeout_seconds,
        )
        workload = _workload_to_dict(response.workload)
        self._workload_cache[workload["workloadId"]] = workload
        return workload

    def start_workload(self, workload_id: str) -> dict[str, Any]:
        return self._run_on_loop(self._start_workload_async(workload_id))

    async def _start_workload_async(self, workload_id: str) -> dict[str, Any]:
        if self._workload_stub is None:
            raise RuntimeError("kernel workload stub is not connected")
        req = self.kernel_pb2.StartWorkloadRequest(workload_id=workload_id)
        response = await self._workload_stub.StartWorkload(
            req,
            metadata=self._metadata(include_session=True),
            timeout=self.config.rpc_timeout_seconds,
        )
        workload = _workload_to_dict(response.workload)
        self._workload_cache[workload["workloadId"]] = workload
        return workload

    def stop_workload(self, workload_id: str) -> dict[str, Any]:
        return self._run_on_loop(self._stop_workload_async(workload_id))

    async def _stop_workload_async(self, workload_id: str) -> dict[str, Any]:
        if self._workload_stub is None:
            raise RuntimeError("kernel workload stub is not connected")
        req = self.kernel_pb2.StopWorkloadRequest(workload_id=workload_id)
        response = await self._workload_stub.StopWorkload(
            req,
            metadata=self._metadata(include_session=True),
            timeout=self.config.rpc_timeout_seconds,
        )
        workload = _workload_to_dict(response.workload)
        self._workload_cache[workload["workloadId"]] = workload
        return workload

    def remove_workload(self, workload_id: str) -> None:
        try:
            self.stop_workload(workload_id)
        except Exception:
            pass
        self._workload_cache.pop(workload_id, None)

    def get_workload_logs(self, workload_id: str) -> dict[str, Any]:
        return self._run_on_loop(self._get_workload_logs_async(workload_id))

    async def _get_workload_logs_async(self, workload_id: str) -> dict[str, Any]:
        if self._workload_stub is None:
            return {"workloadId": workload_id, "logs": []}
        try:
            stream = self._workload_stub.WatchWorkloadLogs(
                self.kernel_pb2.WatchWorkloadLogsRequest(workload_id=workload_id),
                metadata=self._metadata(include_session=True),
            )
            lines: list[dict[str, Any]] = []
            async for log_line in stream:
                lines.append(
                    {
                        "stream": log_line.stream,
                        "line": log_line.line,
                        "timestampUnixMs": log_line.timestamp_unix_ms,
                    }
                )
            return {"workloadId": workload_id, "logs": lines}
        except Exception as exc:
            LOGGER.warning("failed to read workload logs for %s: %s", workload_id, exc)
            return {"workloadId": workload_id, "logs": []}

    def bootstrap_payload(self) -> dict[str, Any]:
        return {
            "providers": self.list_providers(),
            "agents": self.list_agents(),
            "invocations": self.list_invocations(),
            "providerCatalog": self.provider_catalog(),
            "agentTemplates": self.list_agent_templates(),
            "apiAvailable": True,
            "source": "bootstrap",
            "warning": None,
        }

    def _metadata(
        self,
        *,
        include_bootstrap: bool = False,
        include_session: bool = False,
    ) -> list[tuple[str, str]]:
        metadata = [("x-vloop-request-id", str(uuid.uuid4()))]
        if include_bootstrap and self.config.bootstrap_token:
            metadata.append(("x-vloop-bootstrap-token", self.config.bootstrap_token))
        if include_session and self.session_id:
            metadata.append(("x-vloop-session-id", self.session_id))
        return metadata

    async def _sleep_or_stop(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self.shutdown_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            return

    def _state_db_path(self) -> Path:
        return self.config.runtime_root / "state" / "control-plane.sqlite3"


class ControlPlaneApplication:
    def __init__(self, config: ControlPlaneConfig) -> None:
        self.config = config
        self.window_manager = WindowManager(config)
        self.runtime = ControlPlaneRuntime(config, self.window_manager)
        self._runtime_thread: threading.Thread | None = None

    def run(self) -> None:
        self._install_signal_handlers()
        self.window_manager.start(self._start_runtime_thread)

    def _start_runtime_thread(self) -> None:
        if self._runtime_thread and self._runtime_thread.is_alive():
            return

        self._runtime_thread = threading.Thread(
            target=self._run_runtime_thread,
            name="vloop-control-plane-runtime",
            daemon=True,
        )
        self._runtime_thread.start()

    def _run_runtime_thread(self) -> None:
        try:
            asyncio.run(self.runtime.run())
        except Exception:  # pragma: no cover - runtime path
            LOGGER.exception("control-plane runtime crashed")
            raise
        finally:
            self.window_manager.shutdown("control-plane runtime exited")

    def _install_signal_handlers(self) -> None:
        def handle_signal(signum: int, _frame: Any) -> None:
            LOGGER.info("received process signal %s", signum)
            self.runtime.request_shutdown()
            self.window_manager.shutdown(f"received signal {signum}")

        for sig in (signal.SIGINT, signal.SIGTERM):
            with suppress(ValueError):
                signal.signal(sig, handle_signal)


def bootstrap() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    config = load_active_config()
    LOGGER.info(
        "bootstrapping Python control plane against %s with shell %s",
        config.kernel_endpoint,
        config.shell_url(),
    )
    ControlPlaneApplication(config).run()


def _now_unix_ms() -> int:
    return int(time.time() * 1000)


def _workload_to_dict(record: Any) -> dict[str, Any]:
    """Convert a gRPC WorkloadRecord proto to a JSON-safe dict."""
    spec = record.spec
    # `class` and `state` are Python reserved words, so we use getattr
    workload_class = getattr(record, "class", 0)
    workload_state = getattr(record, "state", 0)
    class_map = {
        0: "unspecified",
        1: "harness",
        2: "worker",
        3: "preview",
        4: "service",
    }
    state_map = {
        0: "unspecified",
        1: "created",
        2: "prepared",
        3: "starting",
        4: "running",
        5: "completed",
        6: "failed",
        7: "cancelling",
        8: "cancelled",
        9: "garbage_collected",
    }
    return {
        "workloadId": record.workload_id,
        "class": class_map.get(workload_class, "unspecified"),
        "state": state_map.get(workload_state, "unspecified"),
        "spec": {
            "image": spec.image if spec else "",
            "command": list(spec.command) if spec and spec.command else [],
            "ports": list(spec.ports) if spec and spec.ports else [],
            "environment": dict(spec.environment) if spec and spec.environment else {},
        },
        "createdAtUnixMs": record.created_at_unix_ms,
        "updatedAtUnixMs": record.updated_at_unix_ms,
        "exitCode": record.exit_code,
        "terminationReason": record.termination_reason,
        "exposedPorts": list(record.exposed_ports),
        "previewUrl": record.preview_url,
    }


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not value or not isinstance(value, str):
        raise ValueError(f"missing required string field `{key}`")
    return value
