use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::{
    collections::{BTreeMap, HashMap},
    path::{Path, PathBuf},
    sync::Arc,
    time::{SystemTime, UNIX_EPOCH},
};
use tokio::{fs, io::AsyncWriteExt, sync::RwLock};
use uuid::Uuid;

use crate::proto;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum KernelHealth {
    Starting,
    Ready,
    Degraded,
    DependencyMissing,
    CpUnregistered,
    CpRestarting,
    ShuttingDown,
}

impl Default for KernelHealth {
    fn default() -> Self {
        Self::Starting
    }
}

impl KernelHealth {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Starting => "starting",
            Self::Ready => "ready",
            Self::Degraded => "degraded",
            Self::DependencyMissing => "dependency_missing",
            Self::CpUnregistered => "cp_unregistered",
            Self::CpRestarting => "cp_restarting",
            Self::ShuttingDown => "shutting_down",
        }
    }

    pub fn to_proto(&self) -> i32 {
        match self {
            Self::Starting => proto::KernelHealth::Starting as i32,
            Self::Ready => proto::KernelHealth::Ready as i32,
            Self::Degraded => proto::KernelHealth::Degraded as i32,
            Self::DependencyMissing => proto::KernelHealth::DependencyMissing as i32,
            Self::CpUnregistered => proto::KernelHealth::CpUnregistered as i32,
            Self::CpRestarting => proto::KernelHealth::CpRestarting as i32,
            Self::ShuttingDown => proto::KernelHealth::ShuttingDown as i32,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum DependencyState {
    Ready,
    Missing,
    InstalledButNotRunning,
    VersionMismatch,
    Degraded,
    Disabled,
}

impl DependencyState {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Ready => "ready",
            Self::Missing => "missing",
            Self::InstalledButNotRunning => "installed_but_not_running",
            Self::VersionMismatch => "version_mismatch",
            Self::Degraded => "degraded",
            Self::Disabled => "disabled",
        }
    }

    pub fn to_proto(&self) -> i32 {
        match self {
            Self::Ready => proto::DependencyState::Ready as i32,
            Self::Missing => proto::DependencyState::Missing as i32,
            Self::InstalledButNotRunning => proto::DependencyState::InstalledButNotRunning as i32,
            Self::VersionMismatch => proto::DependencyState::VersionMismatch as i32,
            Self::Degraded => proto::DependencyState::Degraded as i32,
            Self::Disabled => proto::DependencyState::Disabled as i32,
        }
    }

    pub fn is_failure(&self) -> bool {
        matches!(
            self,
            Self::Missing | Self::InstalledButNotRunning | Self::VersionMismatch | Self::Degraded
        )
    }

    pub fn is_critical_failure(&self) -> bool {
        matches!(
            self,
            Self::Missing | Self::InstalledButNotRunning | Self::VersionMismatch
        )
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DependencySnapshot {
    pub name: String,
    pub state: DependencyState,
    pub message: String,
    pub detected_version: Option<String>,
    pub remediation: Option<String>,
    pub checked_at_unix_ms: i64,
    #[serde(default)]
    pub critical: bool,
}

impl DependencySnapshot {
    pub fn to_proto(&self) -> proto::DependencyStatus {
        proto::DependencyStatus {
            name: self.name.clone(),
            state: self.state.to_proto(),
            message: self.message.clone(),
            detected_version: self.detected_version.clone().unwrap_or_default(),
            remediation: self.remediation.clone().unwrap_or_default(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ControlPlaneSession {
    pub registered: bool,
    pub session_id: Option<String>,
    pub version: Option<String>,
    #[serde(default)]
    pub metadata: BTreeMap<String, String>,
    pub registered_at_unix_ms: Option<i64>,
    pub last_heartbeat_at_unix_ms: Option<i64>,
    #[serde(default)]
    pub granted_scopes: Vec<String>,
    #[serde(default)]
    pub announced_capabilities: Vec<String>,
    #[serde(default)]
    pub launch_mode: String,
    #[serde(default)]
    pub status_message: String,
    #[serde(default)]
    pub restart_count: u32,
}

impl ControlPlaneSession {
    pub fn to_proto(&self) -> proto::ControlPlaneStatus {
        proto::ControlPlaneStatus {
            registered: self.registered,
            session_id: self.session_id.clone().unwrap_or_default(),
            version: self.version.clone().unwrap_or_default(),
            registered_at_unix_ms: self.registered_at_unix_ms.unwrap_or_default(),
            last_heartbeat_at_unix_ms: self.last_heartbeat_at_unix_ms.unwrap_or_default(),
            granted_scopes: self.granted_scopes.clone(),
            announced_capabilities: self.announced_capabilities.clone(),
            launch_mode: self.launch_mode.clone(),
            status_message: self.status_message.clone(),
            restart_count: self.restart_count,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KernelPersistentState {
    pub version: String,
    pub boot_id: String,
    pub health: KernelHealth,
    pub status_message: String,
    pub runtime_root: PathBuf,
    pub ipc_endpoint: String,
    pub started_at_unix_ms: i64,
    pub updated_at_unix_ms: i64,
    #[serde(default)]
    pub dependencies: Vec<DependencySnapshot>,
    #[serde(default)]
    pub control_plane: ControlPlaneSession,
}

impl KernelPersistentState {
    pub fn new(
        version: impl Into<String>,
        boot_id: impl Into<String>,
        runtime_root: PathBuf,
        ipc_endpoint: impl Into<String>,
    ) -> Self {
        let now = now_unix_ms();
        Self {
            version: version.into(),
            boot_id: boot_id.into(),
            health: KernelHealth::Starting,
            status_message: "vloopd is booting".into(),
            runtime_root,
            ipc_endpoint: ipc_endpoint.into(),
            started_at_unix_ms: now,
            updated_at_unix_ms: now,
            dependencies: Vec::new(),
            control_plane: ControlPlaneSession {
                launch_mode: "external".into(),
                status_message: "control plane has not registered yet".into(),
                ..Default::default()
            },
        }
    }

    pub fn to_proto(&self) -> proto::KernelSnapshot {
        proto::KernelSnapshot {
            version: self.version.clone(),
            boot_id: self.boot_id.clone(),
            health: self.health.to_proto(),
            status_message: self.status_message.clone(),
            runtime_root: self.runtime_root.display().to_string(),
            ipc_endpoint: self.ipc_endpoint.clone(),
            started_at_unix_ms: self.started_at_unix_ms,
            updated_at_unix_ms: self.updated_at_unix_ms,
            dependencies: self
                .dependencies
                .iter()
                .map(DependencySnapshot::to_proto)
                .collect(),
            control_plane: Some(self.control_plane.to_proto()),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KernelEventRecord {
    pub event_id: String,
    pub event_type: String,
    pub resource_type: String,
    pub resource_id: String,
    pub status: String,
    pub message: String,
    pub timestamp_unix_ms: i64,
    #[serde(default)]
    pub attributes: BTreeMap<String, String>,
}

impl KernelEventRecord {
    pub fn new(
        event_type: impl Into<String>,
        resource_type: impl Into<String>,
        resource_id: impl Into<String>,
        status: impl Into<String>,
        message: impl Into<String>,
    ) -> Self {
        Self {
            event_id: Uuid::new_v4().to_string(),
            event_type: event_type.into(),
            resource_type: resource_type.into(),
            resource_id: resource_id.into(),
            status: status.into(),
            message: message.into(),
            timestamp_unix_ms: now_unix_ms(),
            attributes: BTreeMap::new(),
        }
    }

    pub fn with_attributes(mut self, attributes: BTreeMap<String, String>) -> Self {
        self.attributes = attributes;
        self
    }

    pub fn to_proto(&self) -> proto::KernelEvent {
        proto::KernelEvent {
            event_id: self.event_id.clone(),
            event_type: self.event_type.clone(),
            resource_type: self.resource_type.clone(),
            resource_id: self.resource_id.clone(),
            status: self.status.clone(),
            message: self.message.clone(),
            timestamp_unix_ms: self.timestamp_unix_ms,
            attributes: self
                .attributes
                .clone()
                .into_iter()
                .collect::<HashMap<_, _>>(),
        }
    }
}

#[derive(Clone)]
pub struct StateStore {
    state_path: PathBuf,
    event_log_path: PathBuf,
    inner: Arc<RwLock<KernelPersistentState>>,
}

impl StateStore {
    pub async fn load_or_initialize(
        state_path: PathBuf,
        event_log_path: PathBuf,
        initial_state: KernelPersistentState,
    ) -> Result<Self> {
        let restored = match fs::read(&state_path).await {
            Ok(bytes) => Some(
                serde_json::from_slice::<KernelPersistentState>(&bytes)
                    .with_context(|| format!("failed to parse {}", state_path.display()))?,
            ),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => None,
            Err(error) => {
                return Err(error)
                    .with_context(|| format!("failed to read {}", state_path.display()))
            }
        };

        let mut effective = restored.unwrap_or_else(|| initial_state.clone());
        effective.version = initial_state.version;
        effective.boot_id = initial_state.boot_id;
        effective.health = initial_state.health;
        effective.status_message = initial_state.status_message;
        effective.runtime_root = initial_state.runtime_root;
        effective.ipc_endpoint = initial_state.ipc_endpoint;
        effective.started_at_unix_ms = initial_state.started_at_unix_ms;
        effective.updated_at_unix_ms = now_unix_ms();
        if effective.control_plane.launch_mode.is_empty() {
            effective.control_plane.launch_mode = initial_state.control_plane.launch_mode;
        }
        if effective.control_plane.status_message.is_empty() {
            effective.control_plane.status_message = initial_state.control_plane.status_message;
        }

        let store = Self {
            state_path,
            event_log_path,
            inner: Arc::new(RwLock::new(effective)),
        };
        store.persist_snapshot(&store.snapshot().await).await?;
        Ok(store)
    }

    pub async fn snapshot(&self) -> KernelPersistentState {
        self.inner.read().await.clone()
    }

    pub async fn update<F>(&self, mutator: F) -> Result<KernelPersistentState>
    where
        F: FnOnce(&mut KernelPersistentState),
    {
        let snapshot = {
            let mut guard = self.inner.write().await;
            mutator(&mut guard);
            guard.updated_at_unix_ms = now_unix_ms();
            guard.clone()
        };
        self.persist_snapshot(&snapshot).await?;
        Ok(snapshot)
    }

    pub async fn set_health(
        &self,
        health: KernelHealth,
        message: impl Into<String>,
    ) -> Result<KernelPersistentState> {
        let message = message.into();
        self.update(move |state| {
            state.health = health;
            state.status_message = message;
        })
        .await
    }

    pub async fn set_dependencies(
        &self,
        dependencies: Vec<DependencySnapshot>,
    ) -> Result<KernelPersistentState> {
        self.update(move |state| {
            state.dependencies = dependencies;
        })
        .await
    }

    pub async fn register_control_plane(
        &self,
        session_id: String,
        version: String,
        announced_capabilities: Vec<String>,
        granted_scopes: Vec<String>,
        metadata: BTreeMap<String, String>,
        launch_mode: String,
    ) -> Result<KernelPersistentState> {
        self.update(move |state| {
            let now = now_unix_ms();
            state.control_plane.registered = true;
            state.control_plane.session_id = Some(session_id);
            state.control_plane.version = Some(version);
            state.control_plane.registered_at_unix_ms = Some(now);
            state.control_plane.last_heartbeat_at_unix_ms = Some(now);
            state.control_plane.announced_capabilities = announced_capabilities;
            state.control_plane.granted_scopes = granted_scopes;
            state.control_plane.metadata = metadata;
            state.control_plane.launch_mode = launch_mode;
            state.control_plane.status_message = "control plane session is registered".into();
        })
        .await
    }

    pub async fn heartbeat_control_plane(
        &self,
        session_id: &str,
    ) -> Result<Option<KernelPersistentState>> {
        if !self.current_session_matches(session_id).await {
            return Ok(None);
        }

        let session_id = session_id.to_string();
        let snapshot = self
            .update(move |state| {
                if state.control_plane.session_id.as_deref() == Some(session_id.as_str()) {
                    state.control_plane.last_heartbeat_at_unix_ms = Some(now_unix_ms());
                    state.control_plane.status_message = "control plane heartbeat received".into();
                }
            })
            .await?;

        Ok(Some(snapshot))
    }

    pub async fn clear_control_plane(
        &self,
        message: impl Into<String>,
    ) -> Result<KernelPersistentState> {
        let message = message.into();
        self.update(move |state| {
            state.control_plane.registered = false;
            state.control_plane.session_id = None;
            state.control_plane.version = None;
            state.control_plane.registered_at_unix_ms = None;
            state.control_plane.last_heartbeat_at_unix_ms = None;
            state.control_plane.granted_scopes.clear();
            state.control_plane.announced_capabilities.clear();
            state.control_plane.metadata.clear();
            state.control_plane.status_message = message;
        })
        .await
    }

    pub async fn set_control_plane_launch_mode(
        &self,
        launch_mode: impl Into<String>,
    ) -> Result<KernelPersistentState> {
        let launch_mode = launch_mode.into();
        self.update(move |state| {
            state.control_plane.launch_mode = launch_mode;
        })
        .await
    }

    pub async fn increment_control_plane_restart(
        &self,
        message: impl Into<String>,
    ) -> Result<KernelPersistentState> {
        let message = message.into();
        self.update(move |state| {
            state.control_plane.restart_count = state.control_plane.restart_count.saturating_add(1);
            state.control_plane.status_message = message;
        })
        .await
    }

    pub async fn current_session_matches(&self, session_id: &str) -> bool {
        self.inner.read().await.control_plane.session_id.as_deref() == Some(session_id)
    }

    pub async fn append_event(&self, event: &KernelEventRecord) -> Result<()> {
        let line = serde_json::to_string(event)?;
        let mut file = fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.event_log_path)
            .await
            .with_context(|| format!("failed to open {}", self.event_log_path.display()))?;
        file.write_all(line.as_bytes()).await?;
        file.write_all(b"\n").await?;
        file.flush().await?;
        Ok(())
    }

    async fn persist_snapshot(&self, snapshot: &KernelPersistentState) -> Result<()> {
        persist_json(&self.state_path, snapshot).await
    }
}

pub async fn read_recent_event_records(
    path: &Path,
    limit: usize,
) -> Result<Vec<KernelEventRecord>> {
    let content = match fs::read_to_string(path).await {
        Ok(content) => content,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(error) => {
            return Err(error).with_context(|| format!("failed to read {}", path.display()))
        }
    };

    let mut events = Vec::new();
    for line in content.lines().rev().take(limit) {
        if line.trim().is_empty() {
            continue;
        }
        if let Ok(event) = serde_json::from_str::<KernelEventRecord>(line) {
            events.push(event);
        }
    }
    events.reverse();
    Ok(events)
}

async fn persist_json<T>(path: &Path, value: &T) -> Result<()>
where
    T: Serialize,
{
    let tmp_path = path.with_extension("tmp");
    let bytes = serde_json::to_vec_pretty(value)?;
    fs::write(&tmp_path, bytes)
        .await
        .with_context(|| format!("failed to write {}", tmp_path.display()))?;
    fs::rename(&tmp_path, path)
        .await
        .with_context(|| format!("failed to move {} into place", path.display()))?;
    Ok(())
}

pub fn now_unix_ms() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as i64
}
