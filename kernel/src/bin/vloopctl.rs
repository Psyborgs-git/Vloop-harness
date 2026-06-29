use anyhow::{bail, Context, Result};
use serde::Serialize;
use std::{process::Stdio, time::Duration};
use tokio::{process::Command, time::sleep};
use vloop_kernel::{
    daemon,
    ipc::{self, auth},
    orchestrator::{
        dependencies::{DependencyManager, DoctorCheck, DoctorReport},
        filesystem::RuntimePaths,
        state::{now_unix_ms, read_recent_event_records, DependencyState, KernelPersistentState},
    },
    proto, service,
};

const START_TIMEOUT: Duration = Duration::from_secs(10);
const STOP_TIMEOUT: Duration = Duration::from_secs(10);
const STATUS_POLL_INTERVAL: Duration = Duration::from_millis(300);
const LOG_TAIL_DEFAULT: usize = 50;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum OutputMode {
    Human,
    Json,
}

#[derive(Debug, Clone, Serialize)]
struct DependencyView {
    name: String,
    state: String,
    message: String,
    detected_version: Option<String>,
    remediation: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
struct ControlPlaneView {
    registered: bool,
    session_id: Option<String>,
    version: Option<String>,
    registered_at_unix_ms: Option<i64>,
    last_heartbeat_at_unix_ms: Option<i64>,
    granted_scopes: Vec<String>,
    announced_capabilities: Vec<String>,
    launch_mode: String,
    status_message: String,
    restart_count: u32,
}

#[derive(Debug, Clone, Serialize)]
struct StatusView {
    daemon_reachable: bool,
    source: String,
    version: String,
    boot_id: String,
    health: String,
    status_message: String,
    runtime_root: String,
    ipc_endpoint: String,
    started_at_unix_ms: i64,
    updated_at_unix_ms: i64,
    dependencies: Vec<DependencyView>,
    control_plane: ControlPlaneView,
}

#[derive(Debug, Clone, Serialize)]
struct LogsView {
    event_count: usize,
    events: Vec<vloop_kernel::orchestrator::state::KernelEventRecord>,
}

#[tokio::main]
async fn main() -> Result<()> {
    daemon::init_tracing();
    vloop_kernel::config::load_config_to_env();
    let exit_code = run().await?;
    std::process::exit(exit_code);
}

async fn run() -> Result<i32> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.is_empty() {
        print_help();
        return Ok(1);
    }

    let output_mode = if args.iter().any(|arg| arg == "--json") {
        OutputMode::Json
    } else {
        OutputMode::Human
    };
    let command = args
        .iter()
        .find(|arg| !arg.starts_with("--"))
        .map(|arg| arg.as_str())
        .unwrap_or("");

    let paths = RuntimePaths::detect()?;
    match command {
        "install-service" => install_service(output_mode),
        "uninstall-service" => uninstall_service(output_mode),
        "start" => start(paths, output_mode).await,
        "stop" => stop(paths, output_mode).await,
        "restart" => restart(paths, output_mode).await,
        "status" => status(paths, output_mode).await,
        "open-ui" => open_ui(paths, output_mode).await,
        "logs" => logs(paths, output_mode).await,
        "doctor" => doctor(paths, output_mode).await,
        _ => {
            print_help();
            Ok(1)
        }
    }
}

fn print_help() {
    eprintln!(
        "vloopctl <command> [--json]\nCommands: install-service | uninstall-service | start | stop | restart | status | open-ui | logs | doctor"
    );
}

fn install_service(output_mode: OutputMode) -> Result<i32> {
    let result = service::install_service()?;
    emit(&result, output_mode)?;
    Ok(if result.success { 0 } else { 3 })
}

fn uninstall_service(output_mode: OutputMode) -> Result<i32> {
    let result = service::uninstall_service()?;
    emit(&result, output_mode)?;
    Ok(if result.success { 0 } else { 3 })
}

async fn start(paths: RuntimePaths, output_mode: OutputMode) -> Result<i32> {
    if let Some(status) = query_live_status(&paths).await? {
        emit_message(
            output_mode,
            format!("vloopd is already running with health `{}`", status.health),
            Some(&status),
        )?;
        return Ok(0);
    }

    let daemon_binary = service::sibling_binary("vloopd")?;
    if !daemon_binary.is_file() {
        bail!(
            "could not find sibling vloopd binary at {}",
            daemon_binary.display()
        );
    }

    let repo_root = vloop_kernel::orchestrator::dependencies::detect_repo_root();
    let cp_autostart_str = if control_plane_autostart_enabled() { "true" } else { "false" };

    Command::new(&daemon_binary)
        .env("VLOOP_CP_AUTOSTART", cp_autostart_str)
        .env("VLOOP_REPO_ROOT", repo_root.display().to_string())
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .with_context(|| format!("failed to spawn {}", daemon_binary.display()))?;

    let deadline = tokio::time::Instant::now() + START_TIMEOUT;
    loop {
        if let Some(status) = query_live_status(&paths).await? {
            emit_message(
                output_mode,
                format!("vloopd started with health `{}`", status.health),
                Some(&status),
            )?;
            return Ok(0);
        }

        if tokio::time::Instant::now() >= deadline {
            bail!("timed out while waiting for vloopd to accept IPC connections");
        }

        sleep(STATUS_POLL_INTERVAL).await;
    }
}

async fn stop(paths: RuntimePaths, output_mode: OutputMode) -> Result<i32> {
    let Some(mut client) = connect_client_if_available(&paths).await? else {
        emit_message(
            output_mode,
            "vloopd is not running",
            Option::<&StatusView>::None,
        )?;
        return Ok(0);
    };

    client
        .shutdown(auth::new_request(proto::ShutdownRequest {
            reason: "requested by vloopctl stop".into(),
        }))
        .await
        .context("failed to request daemon shutdown")?;

    let deadline = tokio::time::Instant::now() + STOP_TIMEOUT;
    loop {
        if connect_client_if_available(&paths).await?.is_none() && !paths.lock_file.exists() {
            emit_message(output_mode, "vloopd stopped", Option::<&StatusView>::None)?;
            return Ok(0);
        }

        if tokio::time::Instant::now() >= deadline {
            bail!("timed out while waiting for vloopd to stop");
        }

        sleep(STATUS_POLL_INTERVAL).await;
    }
}

async fn restart(paths: RuntimePaths, output_mode: OutputMode) -> Result<i32> {
    let _ = stop(paths.clone(), OutputMode::Human).await?;
    start(paths, output_mode).await
}

async fn status(paths: RuntimePaths, output_mode: OutputMode) -> Result<i32> {
    if let Some(status) = query_live_status(&paths).await? {
        emit(&status, output_mode)?;
        return Ok(status_exit_code(&status));
    }

    if let Some(last_known) = load_persisted_state(&paths).await? {
        let status = StatusView::from_state(last_known, false, "persisted_state".into());
        emit(&status, output_mode)?;
        return Ok(3);
    }

    emit_message(
        output_mode,
        format!(
            "vloopd is not reachable and no persisted state was found under {}",
            paths.root.display()
        ),
        Option::<&StatusView>::None,
    )?;
    Ok(3)
}

async fn open_ui(paths: RuntimePaths, output_mode: OutputMode) -> Result<i32> {
    let Some(mut client) = connect_client_if_available(&paths).await? else {
        bail!("vloopd is not running; start it before requesting the UI");
    };

    let response = client
        .open_ui(auth::new_request(proto::OpenUiRequest {
            reason: "requested by vloopctl open-ui".into(),
            requestor: "vloopctl".into(),
        }))
        .await;

    match response {
        Ok(response) => {
            let response = response.into_inner();
            emit_message(output_mode, response.message, Option::<&StatusView>::None)?;
            Ok(if response.accepted { 0 } else { 4 })
        }
        Err(error) => {
            emit_message(
                output_mode,
                format!("failed to open the UI: {}", error.message()),
                Option::<&StatusView>::None,
            )?;
            Ok(4)
        }
    }
}

async fn logs(paths: RuntimePaths, output_mode: OutputMode) -> Result<i32> {
    let events = read_recent_event_records(&paths.event_log_file, LOG_TAIL_DEFAULT).await?;
    let view = LogsView {
        event_count: events.len(),
        events,
    };

    match output_mode {
        OutputMode::Json => emit(&view, output_mode)?,
        OutputMode::Human => {
            if view.events.is_empty() {
                println!("no kernel events have been recorded yet");
            } else {
                for event in &view.events {
                    println!(
                        "{} {} {} {} - {}",
                        event.timestamp_unix_ms,
                        event.status,
                        event.event_type,
                        event.resource_id,
                        event.message
                    );
                }
            }
        }
    }

    Ok(0)
}

async fn doctor(paths: RuntimePaths, output_mode: OutputMode) -> Result<i32> {
    let live_status = query_live_status(&paths).await?;
    let persisted_state = load_persisted_state(&paths).await?;
    let dependency_manager =
        DependencyManager::new(paths.clone(), control_plane_autostart_enabled());
    let mut checks = dependency_manager
        .doctor_checks(persisted_state.as_ref())
        .await?;

    checks.insert(0, service_doctor_check());
    checks.insert(1, daemon_binary_doctor_check()?);
    checks.push(daemon_reachability_check(live_status.as_ref()));
    checks.push(ipc_reachability_check(live_status.as_ref(), &paths));
    checks.push(control_plane_registration_check(
        live_status.as_ref(),
        persisted_state.as_ref(),
    ));
    checks.push(launcher_doctor_check()?);
    checks.push(DoctorCheck::new(
        "database_manager",
        DependencyState::Disabled,
        "database lifecycle management is defined in the kernel, but provisioning backends land in a later roadmap stage",
    ));

    let report = DoctorReport {
        generated_at_unix_ms: now_unix_ms(),
        checks,
    };

    match output_mode {
        OutputMode::Json => emit(&report, output_mode)?,
        OutputMode::Human => print_doctor_report(&report),
    }

    Ok(match report.overall_state() {
        DependencyState::Ready | DependencyState::Disabled => 0,
        DependencyState::Missing
        | DependencyState::InstalledButNotRunning
        | DependencyState::VersionMismatch => 2,
        DependencyState::Degraded => 4,
    })
}

fn service_doctor_check() -> DoctorCheck {
    let descriptor = service::descriptor();
    if descriptor.install_supported {
        DoctorCheck::new(
            "service_registration",
            DependencyState::Ready,
            "native service registration is supported on this platform build",
        )
        .with_detail("platform", descriptor.platform)
        .with_detail("label", descriptor.label)
    } else {
        DoctorCheck::new(
            "service_registration",
            DependencyState::Disabled,
            "native service registration is deferred to the packaging stage for this development build",
        )
        .with_detail("platform", descriptor.platform)
        .with_detail("hint", descriptor.control_hint)
    }
}

fn daemon_binary_doctor_check() -> Result<DoctorCheck> {
    let daemon_binary = service::sibling_binary("vloopd")?;
    Ok(if daemon_binary.is_file() {
        DoctorCheck::new(
            "daemon_binary",
            DependencyState::Ready,
            "found sibling vloopd binary for direct start/restart operations",
        )
        .with_detail("path", daemon_binary.display().to_string())
    } else {
        DoctorCheck::new(
            "daemon_binary",
            DependencyState::Missing,
            "could not find sibling vloopd binary",
        )
        .with_detail("path", daemon_binary.display().to_string())
        .with_remediation(
            "Build the kernel binaries so `vloopctl` can start `vloopd` in development.",
        )
    })
}

fn daemon_reachability_check(live_status: Option<&StatusView>) -> DoctorCheck {
    match live_status {
        Some(status) => DoctorCheck::new(
            "daemon_reachability",
            DependencyState::Ready,
            format!(
                "daemon is reachable over IPC with health `{}`",
                status.health
            ),
        )
        .with_detail("ipc_endpoint", status.ipc_endpoint.clone()),
        None => DoctorCheck::new(
            "daemon_reachability",
            DependencyState::Degraded,
            "daemon is not currently reachable over IPC",
        )
        .with_remediation("Run `vloopctl start` and then rerun `vloopctl doctor`.")
        .with_detail("expected_socket", paths_hint()),
    }
}

fn ipc_reachability_check(live_status: Option<&StatusView>, paths: &RuntimePaths) -> DoctorCheck {
    if live_status.is_some() {
        DoctorCheck::new(
            "ipc_endpoint",
            DependencyState::Ready,
            "kernel IPC endpoint is reachable",
        )
        .with_detail("endpoint", paths.ipc_endpoint())
    } else {
        DoctorCheck::new(
            "ipc_endpoint",
            DependencyState::Degraded,
            "kernel IPC endpoint is not reachable",
        )
        .with_detail("endpoint", paths.ipc_endpoint())
        .with_remediation(
            "Ensure `vloopd` is running and owns the socket under the VLoop runtime root.",
        )
    }
}

fn control_plane_registration_check(
    live_status: Option<&StatusView>,
    persisted_state: Option<&KernelPersistentState>,
) -> DoctorCheck {
    if let Some(status) = live_status {
        return if status.control_plane.registered {
            DoctorCheck::new(
                "control_plane_registration",
                DependencyState::Ready,
                "control plane is registered with the kernel",
            )
            .with_detail(
                "session_id",
                status
                    .control_plane
                    .session_id
                    .clone()
                    .unwrap_or_else(|| "unknown".into()),
            )
        } else {
            DoctorCheck::new(
                "control_plane_registration",
                DependencyState::Degraded,
                status.control_plane.status_message.clone(),
            )
            .with_detail("launch_mode", status.control_plane.launch_mode.clone())
            .with_remediation("Start or fix the Python control plane so it can register and heartbeat with the kernel.")
        };
    }

    if let Some(state) = persisted_state {
        return DoctorCheck::new(
            "control_plane_registration",
            DependencyState::Degraded,
            state.control_plane.status_message.clone(),
        )
        .with_detail("launch_mode", state.control_plane.launch_mode.clone())
        .with_remediation(
            "The kernel has not seen a healthy control-plane session for this runtime state.",
        );
    }

    DoctorCheck::new(
        "control_plane_registration",
        DependencyState::Degraded,
        "no control-plane registration has been observed yet",
    )
    .with_remediation("Start `vloopd`, then ensure the Python control plane registers through the kernel IPC endpoint.")
}

fn launcher_doctor_check() -> Result<DoctorCheck> {
    let launcher_binary = service::sibling_binary("vloop-launcher")?;
    Ok(if launcher_binary.is_file() {
        DoctorCheck::new(
            "launcher_binary",
            DependencyState::Ready,
            "found sibling launcher binary",
        )
        .with_detail("path", launcher_binary.display().to_string())
    } else {
        DoctorCheck::new(
            "launcher_binary",
            DependencyState::Missing,
            "could not find sibling launcher binary",
        )
        .with_detail("path", launcher_binary.display().to_string())
        .with_remediation(
            "Build the launcher binary so desktop entrypoints can delegate to the kernel.",
        )
    })
}

fn print_doctor_report(report: &DoctorReport) {
    println!("doctor overall: {}", report.overall_state().as_str());
    for check in &report.checks {
        println!(
            "- {}: {} - {}",
            check.name,
            check.state.as_str(),
            check.message
        );
        if let Some(remediation) = &check.remediation {
            println!("  remediation: {}", remediation);
        }
    }
}

fn emit<T: Serialize>(value: &T, output_mode: OutputMode) -> Result<()> {
    match output_mode {
        OutputMode::Json => println!("{}", serde_json::to_string_pretty(value)?),
        OutputMode::Human => println!("{}", serde_json::to_string_pretty(value)?),
    }
    Ok(())
}

fn emit_message<T: Serialize>(
    output_mode: OutputMode,
    message: impl Into<String>,
    value: Option<&T>,
) -> Result<()> {
    match output_mode {
        OutputMode::Json => {
            #[derive(Serialize)]
            struct MessageEnvelope<'a, T> {
                message: String,
                #[serde(skip_serializing_if = "Option::is_none")]
                value: Option<&'a T>,
            }
            println!(
                "{}",
                serde_json::to_string_pretty(&MessageEnvelope {
                    message: message.into(),
                    value,
                })?
            );
        }
        OutputMode::Human => println!("{}", message.into()),
    }
    Ok(())
}

async fn query_live_status(paths: &RuntimePaths) -> Result<Option<StatusView>> {
    let Some(mut client) = connect_client_if_available(paths).await? else {
        return Ok(None);
    };

    let response = client
        .get_status(auth::new_request(proto::GetStatusRequest {}))
        .await
        .context("failed to query kernel status")?
        .into_inner();
    let snapshot = response
        .snapshot
        .context("kernel did not return a status snapshot")?;
    Ok(Some(StatusView::from_proto(
        snapshot,
        true,
        "live_ipc".into(),
    )))
}

async fn connect_client_if_available(
    paths: &RuntimePaths,
) -> Result<Option<proto::kernel_lifecycle_client::KernelLifecycleClient<tonic::transport::Channel>>>
{
    match ipc::connect_kernel_client(paths).await {
        Ok(client) => Ok(Some(client)),
        Err(_) => Ok(None),
    }
}

async fn load_persisted_state(paths: &RuntimePaths) -> Result<Option<KernelPersistentState>> {
    let content = match tokio::fs::read(paths.state_file.clone()).await {
        Ok(content) => content,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(error) => {
            return Err(error)
                .with_context(|| format!("failed to read {}", paths.state_file.display()))
        }
    };

    let state = serde_json::from_slice::<KernelPersistentState>(&content)
        .with_context(|| format!("failed to parse {}", paths.state_file.display()))?;
    Ok(Some(state))
}

fn status_exit_code(status: &StatusView) -> i32 {
    match status.health.as_str() {
        "ready" => 0,
        "dependency_missing" => 2,
        "starting" | "degraded" | "cp_unregistered" | "cp_restarting" | "shutting_down" => 4,
        _ => 1,
    }
}

fn control_plane_autostart_enabled() -> bool {
    matches!(
        std::env::var("VLOOP_CP_AUTOSTART").as_deref(),
        Ok("1") | Ok("true") | Ok("TRUE") | Ok("yes") | Ok("YES")
    )
}

fn paths_hint() -> String {
    match RuntimePaths::detect() {
        Ok(paths) => paths.ipc_endpoint(),
        Err(_) => "unknown".into(),
    }
}

impl StatusView {
    fn from_state(state: KernelPersistentState, daemon_reachable: bool, source: String) -> Self {
        Self {
            daemon_reachable,
            source,
            version: state.version,
            boot_id: state.boot_id,
            health: state.health.as_str().into(),
            status_message: state.status_message,
            runtime_root: state.runtime_root.display().to_string(),
            ipc_endpoint: state.ipc_endpoint,
            started_at_unix_ms: state.started_at_unix_ms,
            updated_at_unix_ms: state.updated_at_unix_ms,
            dependencies: state
                .dependencies
                .into_iter()
                .map(|dependency| DependencyView {
                    name: dependency.name,
                    state: dependency.state.as_str().into(),
                    message: dependency.message,
                    detected_version: dependency.detected_version,
                    remediation: dependency.remediation,
                })
                .collect(),
            control_plane: ControlPlaneView {
                registered: state.control_plane.registered,
                session_id: state.control_plane.session_id,
                version: state.control_plane.version,
                registered_at_unix_ms: state.control_plane.registered_at_unix_ms,
                last_heartbeat_at_unix_ms: state.control_plane.last_heartbeat_at_unix_ms,
                granted_scopes: state.control_plane.granted_scopes,
                announced_capabilities: state.control_plane.announced_capabilities,
                launch_mode: state.control_plane.launch_mode,
                status_message: state.control_plane.status_message,
                restart_count: state.control_plane.restart_count,
            },
        }
    }

    fn from_proto(snapshot: proto::KernelSnapshot, daemon_reachable: bool, source: String) -> Self {
        let control_plane = snapshot.control_plane.unwrap_or_default();
        Self {
            daemon_reachable,
            source,
            version: snapshot.version,
            boot_id: snapshot.boot_id,
            health: proto::KernelHealth::try_from(snapshot.health)
                .map(kernel_health_to_string)
                .unwrap_or_else(|_| "unknown".into()),
            status_message: snapshot.status_message,
            runtime_root: snapshot.runtime_root,
            ipc_endpoint: snapshot.ipc_endpoint,
            started_at_unix_ms: snapshot.started_at_unix_ms,
            updated_at_unix_ms: snapshot.updated_at_unix_ms,
            dependencies: snapshot
                .dependencies
                .into_iter()
                .map(|dependency| DependencyView {
                    name: dependency.name,
                    state: proto::DependencyState::try_from(dependency.state)
                        .map(dependency_state_to_string)
                        .unwrap_or_else(|_| "unknown".into()),
                    message: dependency.message,
                    detected_version: if dependency.detected_version.is_empty() {
                        None
                    } else {
                        Some(dependency.detected_version)
                    },
                    remediation: if dependency.remediation.is_empty() {
                        None
                    } else {
                        Some(dependency.remediation)
                    },
                })
                .collect(),
            control_plane: ControlPlaneView {
                registered: control_plane.registered,
                session_id: if control_plane.session_id.is_empty() {
                    None
                } else {
                    Some(control_plane.session_id)
                },
                version: if control_plane.version.is_empty() {
                    None
                } else {
                    Some(control_plane.version)
                },
                registered_at_unix_ms: (control_plane.registered_at_unix_ms != 0)
                    .then_some(control_plane.registered_at_unix_ms),
                last_heartbeat_at_unix_ms: (control_plane.last_heartbeat_at_unix_ms != 0)
                    .then_some(control_plane.last_heartbeat_at_unix_ms),
                granted_scopes: control_plane.granted_scopes,
                announced_capabilities: control_plane.announced_capabilities,
                launch_mode: control_plane.launch_mode,
                status_message: control_plane.status_message,
                restart_count: control_plane.restart_count,
            },
        }
    }
}

fn kernel_health_to_string(health: proto::KernelHealth) -> String {
    match health {
        proto::KernelHealth::Starting => "starting",
        proto::KernelHealth::Ready => "ready",
        proto::KernelHealth::Degraded => "degraded",
        proto::KernelHealth::DependencyMissing => "dependency_missing",
        proto::KernelHealth::CpUnregistered => "cp_unregistered",
        proto::KernelHealth::CpRestarting => "cp_restarting",
        proto::KernelHealth::ShuttingDown => "shutting_down",
        proto::KernelHealth::Unspecified => "unspecified",
    }
    .into()
}

fn dependency_state_to_string(state: proto::DependencyState) -> String {
    match state {
        proto::DependencyState::Ready => "ready",
        proto::DependencyState::Missing => "missing",
        proto::DependencyState::InstalledButNotRunning => "installed_but_not_running",
        proto::DependencyState::VersionMismatch => "version_mismatch",
        proto::DependencyState::Degraded => "degraded",
        proto::DependencyState::Disabled => "disabled",
        proto::DependencyState::Unspecified => "unspecified",
    }
    .into()
}
