"""Control-plane runtime — kernel session, heartbeat, event loop, delegation."""

from __future__ import annotations

import asyncio
import importlib
import logging
from contextlib import suppress
from typing import Any

from core.agent import AgentOrchestrator
from core.database import create_database
from core.gateway import ProviderService
from core.vector_store import create_vector_store
from cp.config_service import ControlPlaneConfig, KernelActiveConfig
from cp.events import KernelEventRouter, start_event_router
from cp.http_api import HttpShellServer
from cp.orchestration import OrchestrationMixin, resume_pending_runs_at_startup
from cp.session import make_metadata, now_unix_ms
from cp.snapshots import (
    build_bootstrap_payload,
    build_dependency_snapshot,
    build_event_snapshot,
    build_health_snapshot,
    build_session_snapshot,
    build_system_snapshot,
    build_window_snapshot,
)
from cp.window import WindowManager
from cp.workloads import (
    _create_workload_async,
    _get_workload_async,
    _get_workload_logs_async,
    _list_workloads_async,
    _start_workload_async,
    _stop_workload_async,
)

LOGGER = logging.getLogger("vloop.control_plane")


class ControlPlaneRuntime(OrchestrationMixin):
    """Runs the control plane: kernel registration, HTTP shell, workload pass-through."""

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

        self.kernel_pb2, self.kernel_pb2_grpc = _load_kernel_modules()
        try:
            self.grpc = importlib.import_module("grpc")
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "grpcio is required for the control plane to register with the kernel. "
                "Install control-plane dependencies first."
            ) from exc

        self.db = create_database(self.config.database_url, self.config.runtime_root)
        self.vector_store = create_vector_store(
            self.config.vector_db_url, self.config.runtime_root
        )
        self.provider_service = ProviderService(self.db)
        self.agent_orchestrator = AgentOrchestrator(
            self.db, self.provider_service, self.vector_store
        )

        # Construct and wire the orchestration subsystems (planner, dag_executor,
        # scheduler, checkpoint/approval/memory managers, tool registry, ...) and
        # the runtime accessors the orchestration handlers call.
        self._init_orchestration()

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

    # -- lifecycle -----------------------------------------------------------

    async def run(self) -> None:
        self._loop = asyncio.get_running_loop()
        self.window_manager.set_quit_callback(self._quit_cascade)
        try:
            await self._start_http_shell_if_enabled()

            # Resume any non-terminal Workflow_Runs left by a prior process so
            # they survive a Control_Plane restart (Requirements 3.7, 8.5). A
            # resume failure is logged and swallowed so it never blocks boot.
            self._resume_pending_runs_at_startup()

            backoff = self.config.reconnect_backoff_seconds
            while not self.shutdown_event.is_set():
                try:
                    await self._run_kernel_session()
                    backoff = self.config.reconnect_backoff_seconds
                except Exception as exc:
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

    def _quit_cascade(self) -> None:
        LOGGER.info("quit cascade: stopping HTTP server and requesting shutdown")
        if self.http_server is not None:
            self.http_server.stop()
        self.request_shutdown()
        self.window_manager.shutdown("user requested quit via title-bar or shortcut")

    async def _start_http_shell_if_enabled(self) -> None:
        if not self.config.serve_http:
            return

        self.status = "starting_http"
        self.http_server = HttpShellServer(self)
        self.http_server.start()
        self.window_manager.attach_shell_url(self.config.shell_url())
        self.status = "serving_http"
        LOGGER.info("control-plane HTTP shell ready at %s", self.config.shell_url())

    def _resume_pending_runs_at_startup(self) -> list[str]:
        """Resume non-terminal Workflow_Runs at boot (Requirements 3.7, 8.5).

        Delegates to the orchestration helper, which guards against any failure
        so a resume problem never prevents the Control_Plane from booting
        (Requirement 20.1).
        """
        return resume_pending_runs_at_startup(getattr(self, "dag_executor", None))

    # -- kernel session ------------------------------------------------------

    async def _run_kernel_session(self) -> None:
        self.status = "connecting"
        self.last_error = None
        channel = self.grpc.aio.insecure_channel(
            self.config.kernel_endpoint,
            options=[("grpc.default_authority", "localhost")],
        )
        self._grpc_channel = channel
        self._workload_stub = self.kernel_pb2_grpc.WorkloadControlStub(channel)
        self._wire_execution_manager()
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
            self.last_registered_at_unix_ms = now_unix_ms()
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
            self.last_heartbeat_at_unix_ms = now_unix_ms()
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

    # -- snapshots (delegated to cp.snapshots) ------------------------------

    def health_snapshot(self) -> dict[str, Any]:
        return build_health_snapshot(self)

    def session_snapshot(self) -> dict[str, Any]:
        return build_session_snapshot(self)

    def event_snapshot(self) -> dict[str, Any]:
        return build_event_snapshot(self)

    def window_snapshot(self) -> dict[str, Any]:
        return build_window_snapshot(self)

    def system_snapshot(self) -> dict[str, Any]:
        return build_system_snapshot(self)

    def dependency_snapshot(self) -> dict[str, Any]:
        return build_dependency_snapshot(self)

    # -- provider/agent delegation -------------------------------------------

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

    def get_usage_stats(self) -> dict[str, Any]:
        return self.agent_orchestrator.get_usage_stats()

    def invoke_agent(self, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.agent_orchestrator.invoke_agent(agent_id, payload)

    # -- workload delegation -------------------------------------------------

    def list_workloads(self) -> list[dict[str, Any]]:
        return self._run_on_loop(_list_workloads_async(self))

    def create_workload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._run_on_loop(_create_workload_async(self, payload))

    def get_workload(self, workload_id: str) -> dict[str, Any]:
        return self._run_on_loop(_get_workload_async(self, workload_id))

    def start_workload(self, workload_id: str) -> dict[str, Any]:
        return self._run_on_loop(_start_workload_async(self, workload_id))

    def stop_workload(self, workload_id: str) -> dict[str, Any]:
        return self._run_on_loop(_stop_workload_async(self, workload_id))

    def remove_workload(self, workload_id: str) -> None:
        try:
            self.stop_workload(workload_id)
        except Exception:
            pass
        self._workload_cache.pop(workload_id, None)

    def get_workload_logs(self, workload_id: str) -> dict[str, Any]:
        return self._run_on_loop(_get_workload_logs_async(self, workload_id))

    # -- bootstrap payload ---------------------------------------------------

    def bootstrap_payload(self) -> dict[str, Any]:
        return build_bootstrap_payload(self)

    # -- internal helpers ----------------------------------------------------

    def _run_on_loop(self, coro):
        """Run an async coroutine on the CP's event loop, blocking until complete."""
        if self._loop is None or self._loop.is_closed():
            raise RuntimeError("control-plane event loop is not available")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=self.config.rpc_timeout_seconds)

    def _wire_execution_manager(self) -> None:
        """Build the kernel-backed execution manager once a workload stub exists.

        The orchestration subsystems (Checkpoint_Manager snapshots, DAG_Executor
        workload teardown, secret grants) reach this through a lazy adapter, so
        wiring it here makes those operations live after kernel registration. The
        production stub is async, so awaitables are resolved on the CP event loop
        from the executor's worker threads via :meth:`_run_on_loop`.
        """
        from adapters.rust_infra import RustInfraExecutionManager

        try:
            self._execution_manager = RustInfraExecutionManager(
                self._workload_stub,
                self.kernel_pb2,
                run_sync=self._run_on_loop,
                metadata_provider=lambda: self._metadata(include_session=True),
                rpc_timeout=self.config.rpc_timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001 - never block the kernel session
            LOGGER.exception("failed to wire kernel execution manager: %s", exc)
            self._execution_manager = None

    def _metadata(
        self,
        *,
        include_bootstrap: bool = False,
        include_session: bool = False,
    ) -> list[tuple[str, str]]:
        return make_metadata(
            config=self.config,
            include_bootstrap=include_bootstrap,
            include_session=include_session,
            session_id=self.session_id,
        )

    async def _sleep_or_stop(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self.shutdown_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            return


def _load_kernel_modules():
    from core.generated import load_kernel_modules

    return load_kernel_modules()
