use anyhow::{anyhow, bail, Context, Result};
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

#[cfg(unix)]
use std::os::unix::fs::{FileTypeExt, PermissionsExt};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuntimePaths {
    pub root: PathBuf,
    pub run: PathBuf,
    pub state: PathBuf,
    pub workspaces: PathBuf,
    pub volumes: PathBuf,
    pub artifacts: PathBuf,
    pub logs: PathBuf,
    pub db: PathBuf,
    pub cache: PathBuf,
    pub socket: PathBuf,
    pub socket_owner_file: PathBuf,
    pub lock_file: PathBuf,
    pub state_file: PathBuf,
    pub event_log_file: PathBuf,
}

impl RuntimePaths {
    pub fn detect() -> Result<Self> {
        if let Some(override_root) = std::env::var_os("VLOOP_HOME") {
            return Ok(Self::from_root(PathBuf::from(override_root)));
        }

        let home = std::env::var_os("HOME")
            .or_else(|| std::env::var_os("USERPROFILE"))
            .map(PathBuf::from)
            .ok_or_else(|| {
                anyhow!("could not determine a home directory; set VLOOP_HOME explicitly")
            })?;

        Ok(Self::from_root(home.join(".vloop")))
    }

    pub fn from_root(root: PathBuf) -> Self {
        let run = root.join("run");
        let state = root.join("state");
        let logs = root.join("logs");

        Self {
            socket: run.join("vloopd.sock"),
            socket_owner_file: run.join("vloopd.sock.owner"),
            lock_file: run.join("vloopd.lock"),
            state_file: state.join("kernel-state.json"),
            event_log_file: logs.join("kernel-events.jsonl"),
            workspaces: root.join("workspaces"),
            volumes: root.join("volumes"),
            artifacts: root.join("artifacts"),
            db: root.join("db"),
            cache: root.join("cache"),
            root,
            run,
            state,
            logs,
        }
    }

    pub fn ipc_endpoint(&self) -> String {
        format!("unix://{}", self.socket.display())
    }
}

#[derive(Debug, Clone)]
pub struct FilesystemManager {
    pub paths: RuntimePaths,
}

impl FilesystemManager {
    pub fn new(paths: RuntimePaths) -> Self {
        Self { paths }
    }

    pub async fn initialize(&self) -> Result<()> {
        self.ensure_private_dir(&self.paths.root).await?;
        self.ensure_private_dir(&self.paths.run).await?;
        self.ensure_private_dir(&self.paths.state).await?;
        self.ensure_private_dir(&self.paths.workspaces).await?;
        self.ensure_private_dir(&self.paths.volumes).await?;
        self.ensure_private_dir(&self.paths.artifacts).await?;
        self.ensure_private_dir(&self.paths.logs).await?;
        self.ensure_private_dir(&self.paths.db).await?;
        self.ensure_private_dir(&self.paths.cache).await?;
        Ok(())
    }

    pub async fn ensure_private_dir(&self, path: &Path) -> Result<()> {
        tokio::fs::create_dir_all(path)
            .await
            .with_context(|| format!("failed to create {}", path.display()))?;

        #[cfg(unix)]
        {
            let permissions = std::fs::Permissions::from_mode(0o700);
            std::fs::set_permissions(path, permissions)
                .with_context(|| format!("failed to set permissions on {}", path.display()))?;
        }

        Ok(())
    }

    pub fn assert_managed_path(&self, candidate: &Path) -> Result<PathBuf> {
        let candidate = candidate
            .canonicalize()
            .with_context(|| format!("failed to canonicalize {}", candidate.display()))?;
        let root = self
            .paths
            .root
            .canonicalize()
            .with_context(|| format!("failed to canonicalize {}", self.paths.root.display()))?;

        if !candidate.starts_with(&root) {
            bail!(
                "path {} escapes the managed VLoop runtime root {}",
                candidate.display(),
                root.display()
            );
        }

        Ok(candidate)
    }

    pub fn workspace_path(&self, workspace_id: &str) -> PathBuf {
        self.paths.workspaces.join(workspace_id)
    }

    pub fn volume_path(&self, volume_id: &str) -> PathBuf {
        self.paths.volumes.join(volume_id)
    }

    pub fn artifact_path(&self, workflow_id: &str) -> PathBuf {
        self.paths.artifacts.join(workflow_id)
    }

    pub fn database_path(&self, database_id: &str) -> PathBuf {
        self.paths.db.join(database_id)
    }

    pub fn log_path(&self, name: &str) -> PathBuf {
        self.paths.logs.join(name)
    }

    pub fn runtime_directories(&self) -> Vec<&Path> {
        vec![
            self.paths.root.as_path(),
            self.paths.run.as_path(),
            self.paths.state.as_path(),
            self.paths.workspaces.as_path(),
            self.paths.volumes.as_path(),
            self.paths.artifacts.as_path(),
            self.paths.logs.as_path(),
            self.paths.db.as_path(),
            self.paths.cache.as_path(),
        ]
    }

    pub fn socket_is_safe_to_replace(&self) -> Result<bool> {
        if !self.paths.socket.exists() {
            return Ok(true);
        }

        #[cfg(unix)]
        {
            let metadata = std::fs::symlink_metadata(&self.paths.socket)
                .with_context(|| format!("failed to inspect {}", self.paths.socket.display()))?;
            if metadata.file_type().is_symlink() {
                bail!(
                    "refusing to reuse {} because it is a symlink",
                    self.paths.socket.display()
                );
            }
            if !metadata.file_type().is_socket() {
                bail!(
                    "refusing to reuse {} because it is not a Unix socket",
                    self.paths.socket.display()
                );
            }
        }

        Ok(true)
    }
}
