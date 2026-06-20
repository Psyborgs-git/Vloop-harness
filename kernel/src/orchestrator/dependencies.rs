use anyhow::{Context, Result};
use serde::Serialize;
use std::{
    collections::{BTreeMap, HashMap},
    path::{Path, PathBuf},
};
use tokio::{
    fs,
    process::Command,
    time::{timeout, Duration},
};

use crate::{proto, VERSION};

use super::{
    docker::DockerBackend,
    filesystem::RuntimePaths,
    state::{now_unix_ms, DependencySnapshot, DependencyState, KernelPersistentState},
};

#[derive(Debug, Clone, Serialize)]
pub struct DoctorCheck {
    pub name: String,
    pub state: DependencyState,
    pub message: String,
    pub remediation: Option<String>,
    #[serde(default)]
    pub detail: BTreeMap<String, String>,
}

impl DoctorCheck {
    pub fn new(
        name: impl Into<String>,
        state: DependencyState,
        message: impl Into<String>,
    ) -> Self {
        Self {
            name: name.into(),
            state,
            message: message.into(),
            remediation: None,
            detail: BTreeMap::new(),
        }
    }

    pub fn with_remediation(mut self, remediation: impl Into<String>) -> Self {
        self.remediation = Some(remediation.into());
        self
    }

    pub fn with_detail(mut self, key: impl Into<String>, value: impl Into<String>) -> Self {
        self.detail.insert(key.into(), value.into());
        self
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct DoctorReport {
    pub generated_at_unix_ms: i64,
    pub checks: Vec<DoctorCheck>,
}

impl DoctorReport {
    pub fn overall_state(&self) -> DependencyState {
        if self.checks.iter().any(|check| {
            matches!(
                check.state,
                DependencyState::Missing
                    | DependencyState::InstalledButNotRunning
                    | DependencyState::VersionMismatch
            )
        }) {
            return DependencyState::Missing;
        }

        if self
            .checks
            .iter()
            .any(|check| matches!(check.state, DependencyState::Degraded))
        {
            return DependencyState::Degraded;
        }

        if self
            .checks
            .iter()
            .all(|check| matches!(check.state, DependencyState::Disabled))
        {
            return DependencyState::Disabled;
        }

        DependencyState::Ready
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct ProcessLaunchSpec {
    pub executable: PathBuf,
    pub args: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct DependencyManager {
    paths: RuntimePaths,
    repo_root: PathBuf,
    managed_control_plane: bool,
}

impl DependencyManager {
    pub fn new(paths: RuntimePaths, managed_control_plane: bool) -> Self {
        Self {
            paths,
            repo_root: detect_repo_root(),
            managed_control_plane,
        }
    }

    pub fn repo_root(&self) -> &Path {
        &self.repo_root
    }

    pub fn is_managed_control_plane(&self) -> bool {
        self.managed_control_plane
    }

    pub fn control_plane_entrypoint(&self) -> PathBuf {
        self.repo_root.join("control-plane").join("main.py")
    }

    pub fn control_plane_pyproject(&self) -> PathBuf {
        self.repo_root.join("control-plane").join("pyproject.toml")
    }

    pub fn frontend_package_json(&self) -> PathBuf {
        self.repo_root.join("src").join("package.json")
    }

    pub fn python_command(&self) -> Option<PathBuf> {
        // Prefer the project-local virtual environment Python so the CP has its
        // installed dependencies available even when the system Python doesn't.
        let venv_python = self
            .repo_root
            .join("control-plane")
            .join(".venv")
            .join("bin")
            .join("python3");
        if venv_python.is_file() {
            return Some(venv_python);
        }
        find_executable(&["python3", "python"])
    }

    pub fn control_plane_launch_spec(&self) -> Option<ProcessLaunchSpec> {
        if !self.managed_control_plane {
            return None;
        }

        let executable = self.python_command()?;
        let entrypoint = self.control_plane_entrypoint();
        if !entrypoint.is_file() {
            return None;
        }

        Some(ProcessLaunchSpec {
            executable,
            args: vec!["-u".into(), entrypoint.display().to_string()],
        })
    }

    pub async fn collect_startup_dependencies(&self) -> Result<Vec<DependencySnapshot>> {
        let mut dependencies = vec![DockerBackend::probe().await?];
        dependencies.push(self.python_runtime_snapshot().await?);
        dependencies.push(self.control_plane_python_packages_snapshot().await?);
        dependencies.push(self.control_plane_entrypoint_snapshot().await?);
        Ok(dependencies)
    }

    pub fn active_config(
        &self,
        boot_id: &str,
        ipc_endpoint: &str,
        dependencies: &[DependencySnapshot],
    ) -> proto::KernelActiveConfig {
        let mut features = BTreeMap::new();
        features.insert(
            "control_plane_launch".into(),
            if self.managed_control_plane {
                "managed".into()
            } else {
                "external".into()
            },
        );
        features.insert("kernel_version".into(), VERSION.into());

        if let Some(docker) = dependencies
            .iter()
            .find(|dependency| dependency.name == "docker")
        {
            features.insert("docker".into(), docker.state.as_str().into());
        }

        let mut available_runtimes = Vec::new();
        if dependencies.iter().any(|dependency| {
            dependency.name == "docker" && matches!(dependency.state, DependencyState::Ready)
        }) {
            available_runtimes.push("docker".to_string());
        }

        proto::KernelActiveConfig {
            ipc_endpoint: ipc_endpoint.to_string(),
            boot_id: boot_id.to_string(),
            runtime_root: self.paths.root.display().to_string(),
            available_runtimes,
            features: features.into_iter().collect::<HashMap<_, _>>(),
        }
    }

    pub async fn doctor_checks(
        &self,
        live_status: Option<&KernelPersistentState>,
    ) -> Result<Vec<DoctorCheck>> {
        let mut checks = Vec::new();
        checks.push(self.runtime_directory_check().await?);
        checks.push(self.python_runtime_doctor_check().await?);
        checks.push(self.control_plane_python_packages_doctor_check().await?);
        checks.push(self.control_plane_entrypoint_doctor_check().await?);
        checks.push(self.frontend_bundle_doctor_check().await?);
        checks.push(self.version_compatibility_check().await?);

        let docker = DockerBackend::probe().await?;
        checks.push(
            DoctorCheck::new("docker", docker.state.clone(), docker.message.clone())
                .with_detail(
                    "version",
                    docker.detected_version.unwrap_or_else(|| "unknown".into()),
                )
                .with_remediation(docker.remediation.unwrap_or_else(|| {
                    "Install and start Docker, then rerun `vloopctl doctor`.".into()
                })),
        );

        if let Some(status) = live_status {
            checks.push(
                DoctorCheck::new(
                    "active_kernel_health",
                    if matches!(status.health, super::state::KernelHealth::Ready) {
                        DependencyState::Ready
                    } else {
                        DependencyState::Degraded
                    },
                    format!(
                        "kernel reported health `{}` with message `{}`",
                        status.health.as_str(),
                        status.status_message
                    ),
                )
                .with_detail("ipc_endpoint", status.ipc_endpoint.clone()),
            );
        }

        Ok(checks)
    }

    async fn runtime_directory_check(&self) -> Result<DoctorCheck> {
        let required = [
            (&self.paths.root, "root"),
            (&self.paths.run, "run"),
            (&self.paths.state, "state"),
            (&self.paths.logs, "logs"),
        ];

        let missing: Vec<String> = required
            .iter()
            .filter(|(path, _)| !path.exists())
            .map(|(_, label)| (*label).to_string())
            .collect();

        if missing.is_empty() {
            Ok(DoctorCheck::new(
                "runtime_directories",
                DependencyState::Ready,
                "runtime directories exist",
            )
            .with_detail("root", self.paths.root.display().to_string()))
        } else {
            Ok(DoctorCheck::new(
                "runtime_directories",
                DependencyState::Degraded,
                format!("missing runtime directories: {}", missing.join(", ")),
            )
            .with_remediation("Start `vloopd` once so it can create the managed runtime tree."))
        }
    }

    async fn python_runtime_snapshot(&self) -> Result<DependencySnapshot> {
        let checked_at_unix_ms = now_unix_ms();

        if !self.managed_control_plane {
            return Ok(DependencySnapshot {
                name: "python_runtime".into(),
                state: DependencyState::Disabled,
                message:
                    "managed CP launch is disabled; kernel is waiting for external CP registration"
                        .into(),
                detected_version: None,
                remediation: None,
                checked_at_unix_ms,
                critical: false,
            });
        }

        let python = match self.python_command() {
            Some(path) => path,
            None => {
                return Ok(DependencySnapshot {
                    name: "python_runtime".into(),
                    state: DependencyState::Missing,
                    message: "Python 3 was not found on PATH.".into(),
                    detected_version: None,
                    remediation: Some(
                        "Install Python 3.11+ or configure the control-plane launcher environment."
                            .into(),
                    ),
                    checked_at_unix_ms,
                    critical: true,
                });
            }
        };

        let output = timeout(
            Duration::from_secs(5),
            Command::new(&python).arg("--version").output(),
        )
        .await
        .context("timed out while probing Python")??;

        let version_text = if output.stdout.is_empty() {
            String::from_utf8_lossy(&output.stderr).trim().to_string()
        } else {
            String::from_utf8_lossy(&output.stdout).trim().to_string()
        };

        Ok(DependencySnapshot {
            name: "python_runtime".into(),
            state: if output.status.success() {
                DependencyState::Ready
            } else {
                DependencyState::Degraded
            },
            message: if output.status.success() {
                "Python runtime is available for the control plane.".into()
            } else {
                "Python command exists but did not return a healthy version response.".into()
            },
            detected_version: if version_text.is_empty() {
                None
            } else {
                Some(version_text)
            },
            remediation: if output.status.success() {
                None
            } else {
                Some("Ensure the configured Python runtime can execute `main.py` for the control plane.".into())
            },
            checked_at_unix_ms,
            critical: true,
        })
    }

    async fn control_plane_python_packages_snapshot(&self) -> Result<DependencySnapshot> {
        let checked_at_unix_ms = now_unix_ms();

        if !self.managed_control_plane {
            return Ok(DependencySnapshot {
                name: "control_plane_python_packages".into(),
                state: DependencyState::Disabled,
                message: "managed CP launch is disabled; Python CP package imports are not required for external registration mode".into(),
                detected_version: None,
                remediation: None,
                checked_at_unix_ms,
                critical: false,
            });
        }

        let python = match self.python_command() {
            Some(path) => path,
            None => {
                return Ok(DependencySnapshot {
                    name: "control_plane_python_packages".into(),
                    state: DependencyState::Missing,
                    message: "Python 3 was not found on PATH.".into(),
                    detected_version: None,
                    remediation: Some("Install Python 3.11+ and the control-plane dependencies before enabling managed CP launch.".into()),
                    checked_at_unix_ms,
                    critical: true,
                });
            }
        };

        let output = timeout(
            Duration::from_secs(5),
            Command::new(&python)
                .args([
                    "-c",
                    "import importlib.util; modules=('fastapi','grpc','grpc_tools','uvicorn'); missing=[name for name in modules if importlib.util.find_spec(name) is None]; print(','.join(missing))",
                ])
                .output(),
        )
        .await
        .context("timed out while probing Python control-plane package imports")??;

        let missing_modules = String::from_utf8_lossy(&output.stdout).trim().to_string();
        let packages_ready = output.status.success() && missing_modules.is_empty();

        Ok(DependencySnapshot {
            name: "control_plane_python_packages".into(),
            state: if packages_ready {
                DependencyState::Ready
            } else {
                DependencyState::Missing
            },
            message: if packages_ready {
                "Python control-plane packages are available.".into()
            } else if !missing_modules.is_empty() {
                format!("missing Python control-plane packages: {missing_modules}")
            } else {
                let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
                if stderr.is_empty() {
                    "one or more Python control-plane packages are missing".into()
                } else {
                    stderr
                }
            },
            detected_version: None,
            remediation: if packages_ready {
                None
            } else {
                Some("Install the control-plane Python dependencies (grpcio, grpcio-tools, fastapi, uvicorn) before enabling managed CP launch.".into())
            },
            checked_at_unix_ms,
            critical: true,
        })
    }

    async fn control_plane_entrypoint_snapshot(&self) -> Result<DependencySnapshot> {
        let checked_at_unix_ms = now_unix_ms();
        let entrypoint = self.control_plane_entrypoint();

        if !self.managed_control_plane {
            return Ok(DependencySnapshot {
                name: "control_plane_entrypoint".into(),
                state: DependencyState::Disabled,
                message: "managed CP launch is disabled; control plane entrypoint is not required for kernel readiness".into(),
                detected_version: None,
                remediation: None,
                checked_at_unix_ms,
                critical: false,
            });
        }

        Ok(if entrypoint.is_file() {
            DependencySnapshot {
                name: "control_plane_entrypoint".into(),
                state: DependencyState::Ready,
                message: "control-plane/main.py is present".into(),
                detected_version: None,
                remediation: None,
                checked_at_unix_ms,
                critical: true,
            }
        } else {
            DependencySnapshot {
                name: "control_plane_entrypoint".into(),
                state: DependencyState::Missing,
                message: format!("missing control-plane entrypoint at {}", entrypoint.display()),
                detected_version: None,
                remediation: Some("Restore the Python control-plane bundle or set VLOOP_REPO_ROOT to a valid development checkout.".into()),
                checked_at_unix_ms,
                critical: true,
            }
        })
    }

    async fn python_runtime_doctor_check(&self) -> Result<DoctorCheck> {
        let snapshot = self.python_runtime_snapshot().await?;
        let mut check = DoctorCheck::new("python_runtime", snapshot.state, snapshot.message);
        if let Some(version) = snapshot.detected_version {
            check = check.with_detail("version", version);
        }
        if let Some(remediation) = snapshot.remediation {
            check = check.with_remediation(remediation);
        }
        Ok(check)
    }

    async fn control_plane_python_packages_doctor_check(&self) -> Result<DoctorCheck> {
        let snapshot = self.control_plane_python_packages_snapshot().await?;
        let mut check = DoctorCheck::new(
            "control_plane_python_packages",
            snapshot.state,
            snapshot.message,
        );
        if let Some(remediation) = snapshot.remediation {
            check = check.with_remediation(remediation);
        }
        Ok(check)
    }

    async fn control_plane_entrypoint_doctor_check(&self) -> Result<DoctorCheck> {
        let snapshot = self.control_plane_entrypoint_snapshot().await?;
        let mut check =
            DoctorCheck::new("control_plane_entrypoint", snapshot.state, snapshot.message)
                .with_detail(
                    "path",
                    self.control_plane_entrypoint().display().to_string(),
                );
        if let Some(remediation) = snapshot.remediation {
            check = check.with_remediation(remediation);
        }
        Ok(check)
    }

    async fn frontend_bundle_doctor_check(&self) -> Result<DoctorCheck> {
        let package_json = self.frontend_package_json();
        if !package_json.is_file() {
            return Ok(
                DoctorCheck::new(
                    "frontend_bundle",
                    DependencyState::Degraded,
                    "frontend source package.json was not found",
                )
                .with_detail("path", package_json.display().to_string())
                .with_remediation("Restore the frontend bundle or source tree before expecting the CP to serve the UI."),
            );
        }

        let content = fs::read_to_string(&package_json)
            .await
            .with_context(|| format!("failed to read {}", package_json.display()))?;
        let value: serde_json::Value = serde_json::from_str(&content)
            .with_context(|| format!("failed to parse {}", package_json.display()))?;
        let version = value
            .get("version")
            .and_then(|version| version.as_str())
            .unwrap_or("unknown");

        Ok(DoctorCheck::new(
            "frontend_bundle",
            DependencyState::Ready,
            "frontend source bundle is present",
        )
        .with_detail("version", version.to_string())
        .with_detail("path", package_json.display().to_string()))
    }

    async fn version_compatibility_check(&self) -> Result<DoctorCheck> {
        let cp_version = parse_pyproject_version(&self.control_plane_pyproject()).await?;
        let frontend_version = parse_package_json_version(&self.frontend_package_json()).await?;

        let mut check = DoctorCheck::new(
            "version_compatibility",
            if cp_version.as_deref() == Some(VERSION)
                && frontend_version.as_deref() == Some(VERSION)
            {
                DependencyState::Ready
            } else {
                DependencyState::Degraded
            },
            "checked version alignment between kernel, control plane, and frontend source",
        )
        .with_detail("kernel", VERSION.to_string())
        .with_detail(
            "control_plane",
            cp_version.clone().unwrap_or_else(|| "unknown".into()),
        )
        .with_detail(
            "frontend",
            frontend_version.clone().unwrap_or_else(|| "unknown".into()),
        );

        if check.state == DependencyState::Degraded {
            check = check.with_remediation(
                "Align the package versions across `kernel/Cargo.toml`, `control-plane/pyproject.toml`, and `src/package.json`."
            );
        }

        Ok(check)
    }
}

pub fn detect_repo_root() -> PathBuf {
    if let Some(explicit) = std::env::var_os("VLOOP_REPO_ROOT") {
        return PathBuf::from(explicit);
    }

    if let Ok(current_exe) = std::env::current_exe() {
        for ancestor in current_exe.ancestors() {
            if ancestor.join("README.md").is_file() && ancestor.join("control-plane").is_dir() {
                return ancestor.to_path_buf();
            }
        }
    }

    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .map(Path::to_path_buf)
        .unwrap_or_else(|| PathBuf::from(env!("CARGO_MANIFEST_DIR")))
}

pub fn find_executable(names: &[&str]) -> Option<PathBuf> {
    let path = std::env::var_os("PATH")?;
    let mut candidates = Vec::new();

    for name in names {
        candidates.push((*name).to_string());
        #[cfg(windows)]
        candidates.push(format!("{}.exe", name));
    }

    for directory in std::env::split_paths(&path) {
        for candidate in &candidates {
            let full_path = directory.join(candidate);
            if full_path.is_file() {
                return Some(full_path);
            }
        }
    }

    None
}

async fn parse_pyproject_version(path: &Path) -> Result<Option<String>> {
    let content = match fs::read_to_string(path).await {
        Ok(content) => content,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(error) => {
            return Err(error).with_context(|| format!("failed to read {}", path.display()))
        }
    };

    for line in content.lines() {
        let line = line.trim();
        if let Some(value) = line.strip_prefix("version = ") {
            return Ok(Some(value.trim_matches('"').to_string()));
        }
    }

    Ok(None)
}

async fn parse_package_json_version(path: &Path) -> Result<Option<String>> {
    let content = match fs::read_to_string(path).await {
        Ok(content) => content,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(error) => {
            return Err(error).with_context(|| format!("failed to read {}", path.display()))
        }
    };

    let value: serde_json::Value = serde_json::from_str(&content)
        .with_context(|| format!("failed to parse {}", path.display()))?;
    Ok(value
        .get("version")
        .and_then(|version| version.as_str())
        .map(str::to_string))
}
