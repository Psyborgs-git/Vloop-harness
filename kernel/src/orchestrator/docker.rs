use anyhow::{Context, Result};
use std::path::PathBuf;
use tokio::{
    process::Command,
    time::{timeout, Duration},
};

use super::state::{now_unix_ms, DependencySnapshot, DependencyState};

#[derive(Debug, Clone)]
pub struct DockerBackend;

impl DockerBackend {
    pub async fn probe() -> Result<DependencySnapshot> {
        let checked_at_unix_ms = now_unix_ms();
        let docker = match find_executable(&["docker"]) {
            Some(path) => path,
            None => {
                return Ok(DependencySnapshot {
                    name: "docker".into(),
                    state: DependencyState::Missing,
                    message: "Docker CLI was not found on PATH.".into(),
                    detected_version: None,
                    remediation: Some(
                        "Install Docker Desktop or Docker Engine and ensure the `docker` command is available."
                            .into(),
                    ),
                    checked_at_unix_ms,
                    critical: false,
                });
            }
        };

        let version_output = run_command(&docker, &["--version"]).await;
        let detected_version = match &version_output {
            Ok(output) if output.status.success() => {
                let raw = String::from_utf8_lossy(&output.stdout).trim().to_string();
                if raw.is_empty() {
                    None
                } else {
                    Some(raw)
                }
            }
            _ => None,
        };

        match run_command(&docker, &["info"]).await {
            Ok(output) if output.status.success() => Ok(DependencySnapshot {
                name: "docker".into(),
                state: DependencyState::Ready,
                message: "Docker is installed and responding.".into(),
                detected_version,
                remediation: None,
                checked_at_unix_ms,
                critical: false,
            }),
            Ok(output) => {
                let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
                Ok(DependencySnapshot {
                    name: "docker".into(),
                    state: DependencyState::InstalledButNotRunning,
                    message: if stderr.is_empty() {
                        "Docker is installed but did not answer `docker info`.".into()
                    } else {
                        stderr
                    },
                    detected_version,
                    remediation: Some(
                        "Start Docker Desktop or the Docker Engine service, then rerun `vloopctl doctor`."
                            .into(),
                    ),
                    checked_at_unix_ms,
                    critical: false,
                })
            }
            Err(error) => Ok(DependencySnapshot {
                name: "docker".into(),
                state: DependencyState::Degraded,
                message: format!("failed to probe Docker: {error:#}"),
                detected_version,
                remediation: Some(
                    "Verify Docker is installed and that the current user can talk to the Docker daemon."
                        .into(),
                ),
                checked_at_unix_ms,
                critical: false,
            }),
        }
    }
}

fn find_executable(names: &[&str]) -> Option<PathBuf> {
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

async fn run_command(executable: &PathBuf, args: &[&str]) -> Result<std::process::Output> {
    timeout(
        Duration::from_secs(5),
        Command::new(executable).args(args).output(),
    )
    .await
    .context("timed out while probing Docker")?
    .with_context(|| format!("failed to execute {}", executable.display()))
}
