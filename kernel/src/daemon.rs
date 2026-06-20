use anyhow::{bail, Context, Result};
use async_stream::try_stream;
use futures_util::Stream;
use std::{
    collections::BTreeMap,
    fs::OpenOptions,
    path::{Path, PathBuf},
    pin::Pin,
    process::Stdio,
    sync::Arc,
    time::Duration,
};
use tokio::{
    process::Command,
    sync::{broadcast, watch},
    time::{interval, sleep},
};
#[cfg(unix)]
use tokio_stream::wrappers::UnixListenerStream;
use tonic::{transport::Server, Request, Response, Status};
use tracing::{error, info, warn};
use tracing_subscriber::EnvFilter;
use uuid::Uuid;

use crate::{
    ipc,
    orchestrator::{
        dependencies::{DependencyManager, ProcessLaunchSpec},
        filesystem::{FilesystemManager, RuntimePaths},
        state::{
            now_unix_ms, DependencySnapshot, DependencyState, KernelEventRecord, KernelHealth,
            KernelPersistentState, StateStore,
        },
    },
    proto::{
        self,
        kernel_lifecycle_server::{KernelLifecycle, KernelLifecycleServer},
        workload_control_server::WorkloadControl,
    },
    VERSION,
};

const CONTROL_PLANE_HEARTBEAT_TIMEOUT_MS: i64 = 30_000;
const DEPENDENCY_REFRESH_INTERVAL_SECS: u64 = 60;
const SUPERVISOR_MAX_BACKOFF_SECS: u64 = 30;

pub fn init_tracing() {
    let env_filter = EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info"));
    let _ = tracing_subscriber::fmt()
        .with_env_filter(env_filter)
        .try_init();
}

pub async fn run_daemon() -> Result<()> {
    init_tracing();

    let paths = RuntimePaths::detect()?;
    let filesystem = FilesystemManager::new(paths.clone());
    filesystem.initialize().await?;

    let boot_id = Uuid::new_v4().to_string();
    let _lock = DaemonLock::acquire(&paths, &boot_id).await?;

    let autostart_cp = control_plane_autostart_enabled();
    let dependencies = DependencyManager::new(paths.clone(), autostart_cp);
    let initial_state = KernelPersistentState::new(
        VERSION,
        boot_id.clone(),
        paths.root.clone(),
        paths.ipc_endpoint(),
    );
    let state = StateStore::load_or_initialize(
        paths.state_file.clone(),
        paths.event_log_file.clone(),
        initial_state,
    )
    .await?;

    state
        .set_control_plane_launch_mode(if autostart_cp { "managed" } else { "external" })
        .await?;
    state
        .clear_control_plane("control plane must register for this kernel boot")
        .await?;

    let (event_tx, _) = broadcast::channel(256);
    let (shutdown_tx, shutdown_rx) = watch::channel(false);
    let bootstrap_token = ipc::auth::generate_bootstrap_token();

    let workload_executor = Arc::new(super::orchestrator::executor::WorkloadExecutor::new(
        event_tx.clone(),
    ));
    let workload_store = Arc::new(super::orchestrator::workload_store::WorkloadStore::new(
        workload_executor.clone(),
    ));

    let shared = KernelShared {
        paths: paths.clone(),
        state: state.clone(),
        dependencies,
        event_tx,
        shutdown_tx,
        bootstrap_token,
    };

    shared
        .emit_event(KernelEventRecord::new(
            "kernel.boot",
            "kernel",
            &boot_id,
            "starting",
            "vloopd boot sequence started",
        ))
        .await?;

    shared.refresh_dependencies().await?;

    #[cfg(unix)]
    let listener = ipc::uds::prepare_listener(&paths.socket).await?;
    tokio::fs::write(&paths.socket_owner_file, &boot_id)
        .await
        .with_context(|| format!("failed to write {}", paths.socket_owner_file.display()))?;
    #[cfg(not(unix))]
    bail!("the current kernel build only implements Unix-domain-socket IPC");

    let lifecycle_service = KernelLifecycleService::new(shared.clone());
    let workload_service = WorkloadControlService::new(workload_store.clone(), shared.clone());

    let signal_shared = shared.clone();
    let signal_task = tokio::spawn(async move {
        if let Err(error) = wait_for_os_signal().await {
            error!("failed while waiting for process signals: {error:#}");
            return;
        }

        if let Err(error) = signal_shared
            .begin_shutdown("received process shutdown signal")
            .await
        {
            error!("failed to begin shutdown after signal: {error:#}");
        }
    });

    let refresh_shared = shared.clone();
    let refresh_task = tokio::spawn(async move {
        if let Err(error) = dependency_refresh_loop(refresh_shared).await {
            error!("dependency refresh loop exited unexpectedly: {error:#}");
        }
    });

    let heartbeat_shared = shared.clone();
    let heartbeat_task = tokio::spawn(async move {
        if let Err(error) = control_plane_heartbeat_watchdog(heartbeat_shared).await {
            error!("control-plane heartbeat watchdog exited unexpectedly: {error:#}");
        }
    });

    let supervisor_task = if autostart_cp {
        let supervisor_shared = shared.clone();
        Some(tokio::spawn(async move {
            if let Err(error) = control_plane_supervisor_loop(supervisor_shared).await {
                error!("control-plane supervisor exited unexpectedly: {error:#}");
            }
        }))
    } else {
        None
    };

    info!(socket = %paths.socket.display(), autostart_cp, "vloopd: serving kernel lifecycle IPC");

    let serve_result = Server::builder()
        .add_service(KernelLifecycleServer::new(lifecycle_service))
        .add_service(
            super::proto::workload_control_server::WorkloadControlServer::new(workload_service),
        )
        .serve_with_incoming_shutdown(
            UnixListenerStream::new(listener),
            wait_for_shutdown(shutdown_rx),
        )
        .await;

    shared
        .begin_shutdown("kernel IPC server is stopping")
        .await
        .ok();

    if let Err(error) = serve_result {
        error!("kernel IPC server failed: {error:#}");
        cleanup_runtime_socket_if_owned(&paths, &boot_id).await.ok();
        return Err(error).context("kernel IPC server terminated with an error");
    }

    signal_task.abort();
    refresh_task.abort();
    heartbeat_task.abort();
    if let Some(task) = supervisor_task {
        task.abort();
    }

    cleanup_runtime_socket_if_owned(&paths, &boot_id).await.ok();
    info!("vloopd: shutdown complete");
    Ok(())
}

#[derive(Clone)]
struct KernelShared {
    paths: RuntimePaths,
    state: StateStore,
    dependencies: DependencyManager,
    event_tx: broadcast::Sender<KernelEventRecord>,
    shutdown_tx: watch::Sender<bool>,
    bootstrap_token: String,
}

impl KernelShared {
    async fn refresh_dependencies(&self) -> Result<Vec<DependencySnapshot>> {
        let dependencies = self.dependencies.collect_startup_dependencies().await?;
        self.state.set_dependencies(dependencies.clone()).await?;
        self.recompute_health().await?;
        Ok(dependencies)
    }

    async fn emit_event(&self, event: KernelEventRecord) -> Result<()> {
        self.state.append_event(&event).await?;
        let _ = self.event_tx.send(event);
        Ok(())
    }

    async fn register_control_plane(
        &self,
        version: String,
        capabilities: Vec<String>,
        metadata: BTreeMap<String, String>,
    ) -> Result<(String, Vec<String>, proto::KernelActiveConfig)> {
        let session_id = Uuid::new_v4().to_string();
        let granted_scopes = granted_scopes(&capabilities);
        let dependencies = self.state.snapshot().await.dependencies;
        let active_config = self.dependencies.active_config(
            &self.state.snapshot().await.boot_id,
            &self.paths.ipc_endpoint(),
            &dependencies,
        );

        self.state
            .register_control_plane(
                session_id.clone(),
                version.clone(),
                capabilities.clone(),
                granted_scopes.clone(),
                metadata,
                if self.dependencies.is_managed_control_plane() {
                    "managed".into()
                } else {
                    "external".into()
                },
            )
            .await?;
        self.recompute_health().await?;

        let mut attributes = BTreeMap::new();
        attributes.insert("version".into(), version);
        attributes.insert("session_id".into(), session_id.clone());

        self.emit_event(
            KernelEventRecord::new(
                "control_plane.registered",
                "control_plane",
                session_id.clone(),
                "ready",
                "control plane registered with the kernel",
            )
            .with_attributes(attributes),
        )
        .await?;

        Ok((session_id, granted_scopes, active_config))
    }

    async fn recompute_health(&self) -> Result<KernelPersistentState> {
        let current = self.state.snapshot().await;
        let (next_health, next_message) =
            evaluate_health(&current, self.dependencies.is_managed_control_plane());
        let changed = current.health != next_health || current.status_message != next_message;

        let updated = self
            .state
            .set_health(next_health.clone(), next_message.clone())
            .await?;
        if changed {
            self.emit_event(
                KernelEventRecord::new(
                    "kernel.health.changed",
                    "kernel",
                    updated.boot_id.clone(),
                    next_health.as_str(),
                    next_message,
                )
                .with_attributes(BTreeMap::from([(
                    "health".into(),
                    next_health.as_str().to_string(),
                )])),
            )
            .await?;
        }
        Ok(updated)
    }

    async fn begin_shutdown(&self, reason: impl Into<String>) -> Result<()> {
        let reason = reason.into();
        if *self.shutdown_tx.borrow() {
            return Ok(());
        }

        self.state
            .set_health(KernelHealth::ShuttingDown, reason.clone())
            .await?;
        self.emit_event(KernelEventRecord::new(
            "kernel.shutdown",
            "kernel",
            self.state.snapshot().await.boot_id,
            "shutting_down",
            reason,
        ))
        .await?;
        let _ = self.shutdown_tx.send(true);
        Ok(())
    }
}

#[derive(Clone)]
struct KernelLifecycleService {
    shared: Arc<KernelShared>,
}

impl KernelLifecycleService {
    fn new(shared: KernelShared) -> Self {
        Self {
            shared: Arc::new(shared),
        }
    }
}

#[tonic::async_trait]
impl KernelLifecycle for KernelLifecycleService {
    async fn get_status(
        &self,
        request: Request<proto::GetStatusRequest>,
    ) -> Result<Response<proto::GetStatusResponse>, Status> {
        ipc::auth::require_request_id(request.metadata())?;
        let snapshot = self.shared.state.snapshot().await;
        Ok(Response::new(proto::GetStatusResponse {
            snapshot: Some(snapshot.to_proto()),
        }))
    }

    async fn get_dependencies(
        &self,
        request: Request<proto::GetDependenciesRequest>,
    ) -> Result<Response<proto::GetDependenciesResponse>, Status> {
        ipc::auth::require_request_id(request.metadata())?;
        let snapshot = self.shared.state.snapshot().await;
        let dependencies: Vec<proto::DependencyStatus> =
            snapshot.dependencies.iter().map(|d| d.to_proto()).collect();
        Ok(Response::new(proto::GetDependenciesResponse {
            dependencies,
        }))
    }

    async fn register_control_plane(
        &self,
        request: Request<proto::RegisterControlPlaneRequest>,
    ) -> Result<Response<proto::RegisterControlPlaneResponse>, Status> {
        ipc::auth::require_request_id(request.metadata())?;
        if self.shared.dependencies.is_managed_control_plane() {
            ipc::auth::require_bootstrap_token(request.metadata(), &self.shared.bootstrap_token)?;
        }

        let request = request.into_inner();
        let metadata = request.metadata.into_iter().collect::<BTreeMap<_, _>>();
        let (session_id, granted_scopes, active_config) = self
            .shared
            .register_control_plane(request.version, request.capabilities, metadata)
            .await
            .map_err(|e| {
                error!("register_control_plane failed: {:#}", e);
                internal_status(e)
            })?;

        Ok(Response::new(proto::RegisterControlPlaneResponse {
            session_id,
            granted_scopes,
            active_config: Some(active_config),
        }))
    }

    async fn control_plane_heartbeat(
        &self,
        request: Request<proto::ControlPlaneHeartbeatRequest>,
    ) -> Result<Response<proto::ControlPlaneHeartbeatResponse>, Status> {
        let metadata = request.metadata().clone();
        ipc::auth::require_request_id(&metadata)?;

        let expected = self.shared.state.snapshot().await.control_plane.session_id;
        let Some(expected_session_id) = expected else {
            return Err(Status::failed_precondition(
                "no control-plane session is currently registered",
            ));
        };

        ipc::auth::require_session_id(&metadata, &expected_session_id)?;
        let request = request.into_inner();
        if request.session_id != expected_session_id {
            return Err(Status::unauthenticated("stale or mismatched session id"));
        }

        self.shared
            .state
            .heartbeat_control_plane(&request.session_id)
            .await
            .map_err(internal_status)?
            .ok_or_else(|| Status::unauthenticated("stale or invalid session id"))?;
        let snapshot = self
            .shared
            .recompute_health()
            .await
            .map_err(internal_status)?;

        Ok(Response::new(proto::ControlPlaneHeartbeatResponse {
            acknowledged: true,
            kernel_health: snapshot.health.to_proto(),
        }))
    }

    type WatchKernelEventsStream =
        Pin<Box<dyn Stream<Item = Result<proto::KernelEvent, Status>> + Send + 'static>>;

    async fn watch_kernel_events(
        &self,
        request: Request<proto::WatchKernelEventsRequest>,
    ) -> Result<Response<Self::WatchKernelEventsStream>, Status> {
        let metadata = request.metadata().clone();
        ipc::auth::require_request_id(&metadata)?;

        let expected = self.shared.state.snapshot().await.control_plane.session_id;
        let Some(expected_session_id) = expected else {
            return Err(Status::failed_precondition(
                "no control-plane session is currently registered",
            ));
        };
        ipc::auth::require_session_id(&metadata, &expected_session_id)?;

        let request = request.into_inner();
        let session_id = request.session_id;

        if !self.shared.state.current_session_matches(&session_id).await {
            return Err(Status::unauthenticated("stale or invalid session id"));
        }

        let shared = self.shared.clone();
        let mut rx = self.shared.event_tx.subscribe();
        let stream = try_stream! {
            let snapshot = shared.state.snapshot().await;
            let initial = KernelEventRecord::new(
                "kernel.snapshot",
                "kernel",
                snapshot.boot_id.clone(),
                snapshot.health.as_str(),
                snapshot.status_message.clone(),
            )
            .with_attributes(BTreeMap::from([(
                "health".into(),
                snapshot.health.as_str().to_string(),
            )]));
            yield initial.to_proto();

            loop {
                if !shared.state.current_session_matches(&session_id).await {
                    Err(Status::unauthenticated("stale control-plane session"))?;
                }

                match rx.recv().await {
                    Ok(event) => yield event.to_proto(),
                    Err(broadcast::error::RecvError::Lagged(skipped)) => {
                        yield KernelEventRecord::new(
                            "kernel.event_stream.lagged",
                            "kernel",
                            session_id.clone(),
                            "degraded",
                            format!("kernel event stream skipped {skipped} messages due to lag"),
                        )
                        .to_proto();
                    }
                    Err(broadcast::error::RecvError::Closed) => break,
                }
            }
        };

        Ok(Response::new(
            Box::pin(stream) as Self::WatchKernelEventsStream
        ))
    }

    async fn open_ui(
        &self,
        request: Request<proto::OpenUiRequest>,
    ) -> Result<Response<proto::OpenUiResponse>, Status> {
        ipc::auth::require_request_id(request.metadata())?;
        let request = request.into_inner();
        let snapshot = self.shared.state.snapshot().await;

        if !snapshot.control_plane.registered {
            return Err(Status::failed_precondition(
                "the control plane is not registered, so the UI cannot be opened yet",
            ));
        }

        let mut attributes = BTreeMap::new();
        attributes.insert("requestor".into(), request.requestor.clone());
        attributes.insert("reason".into(), request.reason.clone());

        self.shared
            .emit_event(
                KernelEventRecord::new(
                    "control_plane.open_ui_requested",
                    "control_plane",
                    snapshot
                        .control_plane
                        .session_id
                        .unwrap_or_else(|| "unknown".into()),
                    "accepted",
                    "UI open/focus was requested through the kernel",
                )
                .with_attributes(attributes),
            )
            .await
            .map_err(internal_status)?;

        Ok(Response::new(proto::OpenUiResponse {
            accepted: true,
            message: "control-plane UI open request has been queued".into(),
        }))
    }

    async fn shutdown(
        &self,
        request: Request<proto::ShutdownRequest>,
    ) -> Result<Response<proto::ShutdownResponse>, Status> {
        ipc::auth::require_request_id(request.metadata())?;
        let reason = request.into_inner().reason;
        self.shared
            .begin_shutdown(if reason.is_empty() {
                "shutdown requested by local client".into()
            } else {
                format!("shutdown requested: {reason}")
            })
            .await
            .map_err(internal_status)?;

        Ok(Response::new(proto::ShutdownResponse {
            accepted: true,
            message: "kernel shutdown initiated".into(),
        }))
    }
}

#[derive(Clone)]
struct WorkloadControlService {
    store: Arc<super::orchestrator::workload_store::WorkloadStore>,
    kernel: Arc<KernelShared>,
}

impl WorkloadControlService {
    fn new(
        store: Arc<super::orchestrator::workload_store::WorkloadStore>,
        kernel: KernelShared,
    ) -> Self {
        Self {
            store,
            kernel: Arc::new(kernel),
        }
    }
}

#[tonic::async_trait]
impl super::proto::workload_control_server::WorkloadControl for WorkloadControlService {
    async fn list_workloads(
        &self,
        request: Request<super::proto::ListWorkloadsRequest>,
    ) -> Result<Response<super::proto::ListWorkloadsResponse>, Status> {
        ipc::auth::require_request_id(request.metadata())?;
        let _session = ipc::auth::maybe_session_id(request.metadata());

        let workloads = self.store.list().await;
        let proto_workloads: Vec<_> = workloads
            .iter()
            .map(|w| super::proto::WorkloadRecord {
                workload_id: w.workload_id.clone(),
                class: w.class.to_proto(),
                state: w.state.to_proto(),
                spec: Some(super::proto::WorkloadSpec {
                    image: w.spec.image.clone(),
                    command: w.spec.command.clone(),
                    ports: w.spec.requested_ports.iter().map(|p| *p as u32).collect(),
                    environment: w.spec.merge_environment(),
                    class: w.class.to_proto(),
                }),
                created_at_unix_ms: w.created_at_unix_ms,
                updated_at_unix_ms: w.updated_at_unix_ms,
                exit_code: w.exit_code,
                termination_reason: w.termination_reason.clone().unwrap_or_default(),
                exposed_ports: w.exposed_ports.iter().map(|p| *p as u32).collect(),
                preview_url: w.preview_url.clone().unwrap_or_default(),
            })
            .collect();

        Ok(Response::new(super::proto::ListWorkloadsResponse {
            workloads: proto_workloads,
        }))
    }

    async fn create_workload(
        &self,
        request: Request<super::proto::CreateWorkloadRequest>,
    ) -> Result<Response<super::proto::CreateWorkloadResponse>, Status> {
        ipc::auth::require_request_id(request.metadata())?;
        let _session = ipc::auth::maybe_session_id(request.metadata());

        let req = request.into_inner();
        let spec_proto = req
            .spec
            .ok_or_else(|| Status::invalid_argument("workload spec is required"))?;

        let spec = super::orchestrator::workload::WorkloadSpec {
            image: spec_proto.image,
            command: spec_proto.command,
            env_refs: vec![],
            workspace_id: None,
            requested_ports: spec_proto.ports.iter().map(|p| *p as u16).collect(),
            environment: Some(spec_proto.environment.into_iter().collect()),
            class: Some(super::orchestrator::workload::WorkloadClass::from_proto(
                spec_proto.class,
            )),
        };

        let workflow_id = if req.workflow_id.is_empty() {
            None
        } else {
            Some(req.workflow_id)
        };

        let record = self
            .store
            .create(spec, workflow_id)
            .await
            .map_err(|e| Status::internal(format!("failed to create workload: {e}")))?;

        let proto_record = super::proto::WorkloadRecord {
            workload_id: record.workload_id.clone(),
            class: record.class.to_proto(),
            state: record.state.to_proto(),
            spec: Some(super::proto::WorkloadSpec {
                image: record.spec.image.clone(),
                command: record.spec.command.clone(),
                ports: record
                    .spec
                    .requested_ports
                    .iter()
                    .map(|p| *p as u32)
                    .collect(),
                environment: record.spec.merge_environment(),
                class: record.class.to_proto(),
            }),
            created_at_unix_ms: record.created_at_unix_ms,
            updated_at_unix_ms: record.updated_at_unix_ms,
            exit_code: record.exit_code,
            termination_reason: record.termination_reason.clone().unwrap_or_default(),
            exposed_ports: record.exposed_ports.iter().map(|p| *p as u32).collect(),
            preview_url: record.preview_url.clone().unwrap_or_default(),
        };

        Ok(Response::new(super::proto::CreateWorkloadResponse {
            workload: Some(proto_record),
        }))
    }

    async fn start_workload(
        &self,
        request: Request<super::proto::StartWorkloadRequest>,
    ) -> Result<Response<super::proto::StartWorkloadResponse>, Status> {
        ipc::auth::require_request_id(request.metadata())?;
        let _session = ipc::auth::maybe_session_id(request.metadata());

        let req = request.into_inner();
        let record = self
            .store
            .start(&req.workload_id)
            .await
            .map_err(|e| Status::internal(format!("failed to start workload: {e}")))?;

        let proto_record = super::proto::WorkloadRecord {
            workload_id: record.workload_id.clone(),
            class: record.class.to_proto(),
            state: record.state.to_proto(),
            spec: Some(super::proto::WorkloadSpec {
                image: record.spec.image.clone(),
                command: record.spec.command.clone(),
                ports: record
                    .spec
                    .requested_ports
                    .iter()
                    .map(|p| *p as u32)
                    .collect(),
                environment: record.spec.merge_environment(),
                class: record.class.to_proto(),
            }),
            created_at_unix_ms: record.created_at_unix_ms,
            updated_at_unix_ms: record.updated_at_unix_ms,
            exit_code: record.exit_code,
            termination_reason: record.termination_reason.clone().unwrap_or_default(),
            exposed_ports: record.exposed_ports.iter().map(|p| *p as u32).collect(),
            preview_url: record.preview_url.clone().unwrap_or_default(),
        };

        Ok(Response::new(super::proto::StartWorkloadResponse {
            workload: Some(proto_record),
        }))
    }

    async fn stop_workload(
        &self,
        request: Request<super::proto::StopWorkloadRequest>,
    ) -> Result<Response<super::proto::StopWorkloadResponse>, Status> {
        ipc::auth::require_request_id(request.metadata())?;
        let _session = ipc::auth::maybe_session_id(request.metadata());

        let req = request.into_inner();
        let record = self
            .store
            .stop(&req.workload_id)
            .await
            .map_err(|e| Status::internal(format!("failed to stop workload: {e}")))?;

        let proto_record = super::proto::WorkloadRecord {
            workload_id: record.workload_id.clone(),
            class: record.class.to_proto(),
            state: record.state.to_proto(),
            spec: Some(super::proto::WorkloadSpec {
                image: record.spec.image.clone(),
                command: record.spec.command.clone(),
                ports: record
                    .spec
                    .requested_ports
                    .iter()
                    .map(|p| *p as u32)
                    .collect(),
                environment: record.spec.merge_environment(),
                class: record.class.to_proto(),
            }),
            created_at_unix_ms: record.created_at_unix_ms,
            updated_at_unix_ms: record.updated_at_unix_ms,
            exit_code: record.exit_code,
            termination_reason: record.termination_reason.clone().unwrap_or_default(),
            exposed_ports: record.exposed_ports.iter().map(|p| *p as u32).collect(),
            preview_url: record.preview_url.clone().unwrap_or_default(),
        };

        Ok(Response::new(super::proto::StopWorkloadResponse {
            workload: Some(proto_record),
        }))
    }

    type WatchWorkloadLogsStream =
        Pin<Box<dyn Stream<Item = Result<super::proto::WorkloadLogLine, Status>> + Send + 'static>>;

    async fn watch_workload_logs(
        &self,
        request: Request<super::proto::WatchWorkloadLogsRequest>,
    ) -> Result<Response<Self::WatchWorkloadLogsStream>, Status> {
        ipc::auth::require_request_id(request.metadata())?;
        let _session = ipc::auth::maybe_session_id(request.metadata());

        let req = request.into_inner();
        let store = self.store.clone();
        let workload_id = req.workload_id.clone();

        let stream = try_stream! {
            let logs = store.get_logs(&workload_id).await.map_err(|e| {
                Status::internal(format!("failed to get logs: {e}"))
            })?;

            for (line, stream_type) in logs {
                yield super::proto::WorkloadLogLine {
                    workload_id: workload_id.clone(),
                    stream: stream_type,
                    line,
                    timestamp_unix_ms: now_unix_ms(),
                };
            }
        };

        Ok(Response::new(
            Box::pin(stream) as Self::WatchWorkloadLogsStream
        ))
    }

    async fn get_workload(
        &self,
        request: Request<super::proto::GetWorkloadRequest>,
    ) -> Result<Response<super::proto::GetWorkloadResponse>, Status> {
        ipc::auth::require_request_id(request.metadata())?;
        let _session = ipc::auth::maybe_session_id(request.metadata());

        let req = request.into_inner();
        let record =
            self.store.get(&req.workload_id).await.ok_or_else(|| {
                Status::not_found(format!("workload {} not found", req.workload_id))
            })?;

        let proto_record = super::proto::WorkloadRecord {
            workload_id: record.workload_id.clone(),
            class: record.class.to_proto(),
            state: record.state.to_proto(),
            spec: Some(super::proto::WorkloadSpec {
                image: record.spec.image.clone(),
                command: record.spec.command.clone(),
                ports: record
                    .spec
                    .requested_ports
                    .iter()
                    .map(|p| *p as u32)
                    .collect(),
                environment: record.spec.merge_environment(),
                class: record.class.to_proto(),
            }),
            created_at_unix_ms: record.created_at_unix_ms,
            updated_at_unix_ms: record.updated_at_unix_ms,
            exit_code: record.exit_code,
            termination_reason: record.termination_reason.clone().unwrap_or_default(),
            exposed_ports: record.exposed_ports.iter().map(|p| *p as u32).collect(),
            preview_url: record.preview_url.clone().unwrap_or_default(),
        };

        Ok(Response::new(super::proto::GetWorkloadResponse {
            workload: Some(proto_record),
        }))
    }
}

async fn dependency_refresh_loop(shared: KernelShared) -> Result<()> {
    let mut ticker = interval(Duration::from_secs(DEPENDENCY_REFRESH_INTERVAL_SECS));
    loop {
        tokio::select! {
            _ = ticker.tick() => {
                if let Err(error) = shared.refresh_dependencies().await {
                    warn!("dependency refresh failed: {error:#}");
                }
            }
            _ = wait_for_shutdown(shared.shutdown_tx.subscribe()) => break,
        }
    }
    Ok(())
}

async fn control_plane_heartbeat_watchdog(shared: KernelShared) -> Result<()> {
    let mut ticker = interval(Duration::from_secs(5));
    loop {
        tokio::select! {
            _ = ticker.tick() => {
                let snapshot = shared.state.snapshot().await;
                let Some(last_heartbeat_at_unix_ms) = snapshot.control_plane.last_heartbeat_at_unix_ms else {
                    continue;
                };

                if snapshot.control_plane.registered
                    && now_unix_ms() - last_heartbeat_at_unix_ms > CONTROL_PLANE_HEARTBEAT_TIMEOUT_MS
                {
                    let session_id = snapshot.control_plane.session_id.unwrap_or_else(|| "unknown".into());
                    shared
                        .state
                        .clear_control_plane("control plane heartbeat timed out")
                        .await?;
                    shared.recompute_health().await?;
                    shared.emit_event(KernelEventRecord::new(
                        "control_plane.heartbeat_timed_out",
                        "control_plane",
                        session_id,
                        "degraded",
                        "control plane heartbeat timed out and the session was invalidated",
                    )).await?;
                }
            }
            _ = wait_for_shutdown(shared.shutdown_tx.subscribe()) => break,
        }
    }
    Ok(())
}

async fn control_plane_supervisor_loop(shared: KernelShared) -> Result<()> {
    let Some(spec) = shared.dependencies.control_plane_launch_spec() else {
        warn!("managed control-plane autostart is enabled but no launch spec could be resolved");
        shared.recompute_health().await?;
        return Ok(());
    };

    let stdout_path = shared.paths.logs.join("control-plane.stdout.log");
    let stderr_path = shared.paths.logs.join("control-plane.stderr.log");
    let mut backoff = Duration::from_secs(2);

    loop {
        if *shared.shutdown_tx.borrow() {
            break;
        }

        if !managed_control_plane_launch_ready(&shared).await {
            tokio::select! {
                _ = sleep(backoff) => {}
                _ = wait_for_shutdown(shared.shutdown_tx.subscribe()) => break,
            }
            backoff = std::cmp::min(
                backoff.saturating_mul(2),
                Duration::from_secs(SUPERVISOR_MAX_BACKOFF_SECS),
            );
            continue;
        }

        launch_control_plane_process(&shared, &spec, &stdout_path, &stderr_path).await?;
        let exit_message =
            monitor_control_plane_process(&shared, &spec, &stdout_path, &stderr_path).await?;

        shared
            .state
            .increment_control_plane_restart(exit_message.clone())
            .await?;
        shared
            .state
            .clear_control_plane(exit_message.clone())
            .await?;
        shared.recompute_health().await?;
        shared
            .emit_event(KernelEventRecord::new(
                "control_plane.restarting",
                "control_plane",
                spec.executable.display().to_string(),
                "restarting",
                exit_message,
            ))
            .await?;

        tokio::select! {
            _ = sleep(backoff) => {}
            _ = wait_for_shutdown(shared.shutdown_tx.subscribe()) => break,
        }
        backoff = std::cmp::min(
            backoff.saturating_mul(2),
            Duration::from_secs(SUPERVISOR_MAX_BACKOFF_SECS),
        );
    }

    Ok(())
}

async fn launch_control_plane_process(
    shared: &KernelShared,
    spec: &ProcessLaunchSpec,
    stdout_path: &Path,
    _stderr_path: &Path,
) -> Result<()> {
    shared
        .state
        .clear_control_plane("control plane process launched; waiting for registration")
        .await?;
    shared.recompute_health().await?;
    shared
        .emit_event(KernelEventRecord::new(
            "control_plane.launching",
            "control_plane",
            spec.executable.display().to_string(),
            "starting",
            "launching managed Python control plane",
        ))
        .await?;

    let _ = stdout_path;
    Ok(())
}

async fn monitor_control_plane_process(
    shared: &KernelShared,
    spec: &ProcessLaunchSpec,
    stdout_path: &Path,
    stderr_path: &Path,
) -> Result<String> {
    let stdout = OpenOptions::new()
        .create(true)
        .append(true)
        .open(stdout_path)
        .with_context(|| format!("failed to open {}", stdout_path.display()))?;
    let stderr = OpenOptions::new()
        .create(true)
        .append(true)
        .open(stderr_path)
        .with_context(|| format!("failed to open {}", stderr_path.display()))?;

    let mut child = Command::new(&spec.executable)
        .args(&spec.args)
        .current_dir(shared.dependencies.repo_root())
        .env("VLOOP_KERNEL_ENDPOINT", shared.paths.ipc_endpoint())
        .env(
            "VLOOP_KERNEL_BOOTSTRAP_TOKEN",
            shared.bootstrap_token.clone(),
        )
        .env(
            "VLOOP_RUNTIME_ROOT",
            shared.paths.root.display().to_string(),
        )
        .env(
            "VLOOP_REPO_ROOT",
            shared.dependencies.repo_root().display().to_string(),
        )
        .stdin(Stdio::null())
        .stdout(Stdio::from(stdout))
        .stderr(Stdio::from(stderr))
        .spawn()
        .with_context(|| format!("failed to spawn {}", spec.executable.display()))?;

    let child_result = tokio::select! {
        result = child.wait() => Some(result),
        _ = wait_for_shutdown(shared.shutdown_tx.subscribe()) => {
            let _ = child.start_kill();
            let _ = child.wait().await;
            None
        }
    };

    let Some(result) = child_result else {
        return Ok("managed control plane stopped during kernel shutdown".into());
    };

    let status = result
        .with_context(|| format!("failed while waiting for {}", spec.executable.display()))?;
    Ok(match status.code() {
        Some(code) => format!("managed control plane exited with code {code}"),
        None => "managed control plane exited without an exit code".into(),
    })
}

async fn managed_control_plane_launch_ready(shared: &KernelShared) -> bool {
    let snapshot = shared.state.snapshot().await;
    !snapshot.dependencies.iter().any(|dependency| {
        dependency.critical
            && matches!(
                dependency.state,
                DependencyState::Missing
                    | DependencyState::InstalledButNotRunning
                    | DependencyState::VersionMismatch
                    | DependencyState::Degraded
            )
            && matches!(
                dependency.name.as_str(),
                "python_runtime" | "control_plane_python_packages" | "control_plane_entrypoint"
            )
    })
}

fn granted_scopes(capabilities: &[String]) -> Vec<String> {
    if capabilities.is_empty() {
        return vec![
            "kernel.events".into(),
            "kernel.status".into(),
            "kernel.open_ui".into(),
        ];
    }

    capabilities.to_vec()
}

fn evaluate_health(
    snapshot: &KernelPersistentState,
    managed_control_plane: bool,
) -> (KernelHealth, String) {
    if matches!(snapshot.health, KernelHealth::ShuttingDown) {
        return (KernelHealth::ShuttingDown, snapshot.status_message.clone());
    }

    if let Some(dependency) = snapshot
        .dependencies
        .iter()
        .find(|dependency| dependency.critical && dependency.state.is_critical_failure())
    {
        return (
            KernelHealth::DependencyMissing,
            format!(
                "critical dependency `{}` is {}: {}",
                dependency.name,
                dependency.state.as_str(),
                dependency.message
            ),
        );
    }

    let degraded_dependencies = snapshot
        .dependencies
        .iter()
        .filter(|dependency| {
            dependency.critical && matches!(dependency.state, DependencyState::Degraded)
        })
        .count();

    if snapshot.control_plane.registered {
        if degraded_dependencies > 0 {
            return (
                KernelHealth::Degraded,
                "control plane is registered, but one or more critical dependencies are degraded"
                    .into(),
            );
        }

        return (KernelHealth::Ready, "kernel ready".into());
    }

    if managed_control_plane && snapshot.control_plane.restart_count > 0 {
        return (
            KernelHealth::CpRestarting,
            snapshot.control_plane.status_message.clone(),
        );
    }

    (
        KernelHealth::CpUnregistered,
        if snapshot.control_plane.status_message.is_empty() {
            "waiting for control plane registration".into()
        } else {
            snapshot.control_plane.status_message.clone()
        },
    )
}

fn control_plane_autostart_enabled() -> bool {
    matches!(
        std::env::var("VLOOP_CP_AUTOSTART").as_deref(),
        Ok("1") | Ok("true") | Ok("TRUE") | Ok("yes") | Ok("YES")
    )
}

fn internal_status(error: anyhow::Error) -> Status {
    Status::internal(error.to_string())
}

async fn wait_for_shutdown(mut shutdown_rx: watch::Receiver<bool>) {
    loop {
        if *shutdown_rx.borrow() {
            break;
        }
        if shutdown_rx.changed().await.is_err() {
            break;
        }
    }
}

async fn cleanup_runtime_socket_if_owned(paths: &RuntimePaths, boot_id: &str) -> Result<()> {
    let owner = match tokio::fs::read_to_string(&paths.socket_owner_file).await {
        Ok(owner) => owner,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(()),
        Err(error) => {
            return Err(error)
                .with_context(|| format!("failed to read {}", paths.socket_owner_file.display()))
        }
    };

    if owner.trim() != boot_id {
        return Ok(());
    }

    ipc::uds::cleanup_socket(&paths.socket).await?;
    match tokio::fs::remove_file(&paths.socket_owner_file).await {
        Ok(_) => {}
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
        Err(error) => {
            return Err(error)
                .with_context(|| format!("failed to remove {}", paths.socket_owner_file.display()))
        }
    }

    Ok(())
}

async fn wait_for_os_signal() -> Result<()> {
    #[cfg(unix)]
    {
        use tokio::signal::unix::{signal, SignalKind};
        let mut terminate =
            signal(SignalKind::terminate()).context("failed to install SIGTERM handler")?;
        tokio::select! {
            _ = tokio::signal::ctrl_c() => {}
            _ = terminate.recv() => {}
        }
        return Ok(());
    }

    #[cfg(not(unix))]
    {
        tokio::signal::ctrl_c()
            .await
            .context("failed to wait for Ctrl-C")?;
        Ok(())
    }
}

struct DaemonLock {
    path: PathBuf,
    boot_id: String,
}

impl DaemonLock {
    async fn acquire(paths: &RuntimePaths, boot_id: &str) -> Result<Self> {
        if paths.lock_file.exists() {
            #[cfg(unix)]
            {
                if tokio::net::UnixStream::connect(&paths.socket).await.is_ok() {
                    bail!(
                        "a VLoop daemon is already running for {}",
                        paths.root.display()
                    );
                }
            }
            match tokio::fs::remove_file(&paths.lock_file).await {
                Ok(_) => {}
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
                Err(error) => {
                    return Err(error).with_context(|| {
                        format!(
                            "failed to clear stale lock file {}",
                            paths.lock_file.display()
                        )
                    })
                }
            }
        }

        let mut file = tokio::fs::OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(&paths.lock_file)
            .await
            .with_context(|| format!("failed to create {}", paths.lock_file.display()))?;

        use tokio::io::AsyncWriteExt;
        file.write_all(format!("pid={}\nboot_id={}\n", std::process::id(), boot_id).as_bytes())
            .await
            .with_context(|| format!("failed to write {}", paths.lock_file.display()))?;
        file.flush().await.ok();

        Ok(Self {
            path: paths.lock_file.clone(),
            boot_id: boot_id.to_string(),
        })
    }
}

impl Drop for DaemonLock {
    fn drop(&mut self) {
        let should_remove = std::fs::read_to_string(&self.path)
            .map(|contents| contents.contains(&format!("boot_id={}", self.boot_id)))
            .unwrap_or(false);
        if should_remove {
            let _ = std::fs::remove_file(&self.path);
        }
    }
}
