use anyhow::{anyhow, bail, Context, Result};
use serde::{Deserialize, Serialize};
use std::{path::PathBuf, time::Duration};
use tokio::process::Command;
use tokio::time::timeout;
use tracing::{info, warn};

use super::state::{now_unix_ms, KernelEventRecord};
use super::workload::{WorkloadClass, WorkloadLifecycleState, WorkloadRecord, WorkloadSpec};

const DOCKER_TIMEOUT: Duration = Duration::from_secs(120);

#[derive(Debug, Clone)]
pub struct WorkloadExecutor {
    event_tx: tokio::sync::broadcast::Sender<KernelEventRecord>,
}

impl WorkloadExecutor {
    pub fn new(event_tx: tokio::sync::broadcast::Sender<KernelEventRecord>) -> Self {
        Self { event_tx }
    }

    fn emit(&self, event: KernelEventRecord) {
        let _ = self.event_tx.send(event);
    }

    pub async fn create_workload(
        &self,
        spec: WorkloadSpec,
        _workflow_id: Option<String>,
    ) -> Result<WorkloadRecord> {
        let workload_id = uuid::Uuid::new_v4().to_string();
        let now = now_unix_ms();

        let class = spec.class.clone().unwrap_or(WorkloadClass::Worker);

        let record = WorkloadRecord {
            workload_id: workload_id.clone(),
            class: class.clone(),
            state: WorkloadLifecycleState::Created,
            spec: spec.clone(),
            created_at_unix_ms: now,
            updated_at_unix_ms: now,
            exit_code: None,
            termination_reason: None,
            exposed_ports: vec![],
            preview_url: None,
            container_id: None,
        };

        self.emit(KernelEventRecord::new(
            "workload.created",
            "workload",
            &workload_id,
            "created",
            &format!(
                "Workload {} created: image={}",
                &workload_id[..8],
                &record.spec.image
            ),
        ));

        Ok(record)
    }

    pub async fn start_workload(&self, record: &mut WorkloadRecord) -> Result<()> {
        // Pre-check: provide a clear error when Docker is not available so the
        // user can fix it from the UI Setup view instead of getting a raw
        // "command not found" panic.
        find_docker().map_err(|_e| {
            anyhow!(
                "Docker is not available. Install Docker to run workloads. \
                 Open the Setup view in the VLoop UI for install instructions."
            )
        })?;

        let mut args: Vec<String> = vec![
            "run".into(),
            "--rm".into(),
            "-d".into(),
            "--label".into(),
            format!("vloop.workload_id={}", record.workload_id),
        ];

        for (key, value) in record.spec.merge_environment() {
            args.push("-e".into());
            args.push(format!("{key}={value}"));
        }

        for port in &record.spec.requested_ports {
            args.push("-p".into());
            args.push(format!("{port}:{port}"));
        }

        if !record.spec.command.is_empty() {
            args.push("--entrypoint".into());
            args.push(record.spec.command[0].clone());
        }

        args.push(record.spec.image.clone());

        let docker = find_docker()?;
        let docker_display = docker.display().to_string();
        info!(
            "Starting Docker workload container with `{} {}`",
            docker_display,
            args.join(" ")
        );

        let output = timeout(DOCKER_TIMEOUT, async {
            Command::new(&docker).args(&args).output().await
        })
        .await
        .map_err(|_| anyhow!("timed out while spawning Docker container"))?
        .with_context(|| format!("failed to run `{}`", docker.display()))?;

        let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
            let err_msg = if stderr.is_empty() { stdout } else { stderr };
            bail!("docker run failed: {err_msg}");
        }

        let container_id = stdout.trim().to_string();
        let now = now_unix_ms();

        record.container_id = Some(container_id.clone());
        record.state = WorkloadLifecycleState::Running;
        record.updated_at_unix_ms = now;

        if !record.spec.requested_ports.is_empty() {
            record.exposed_ports = record.spec.requested_ports.clone();
            if let Some(first_port) = record.spec.requested_ports.first() {
                record.preview_url = Some(format!("http://localhost:{first_port}"));
            }
        }

        self.emit(KernelEventRecord::new(
            "workload.started",
            "workload",
            &record.workload_id,
            "running",
            &format!("Docker container {} is running", &container_id[..12]),
        ));

        info!(
            workload_id = %record.workload_id,
            container_id = %container_id,
            "Workload container started"
        );

        Ok(())
    }

    pub async fn stop_workload(&self, record: &mut WorkloadRecord) -> Result<()> {
        let container_id = record
            .container_id
            .as_ref()
            .ok_or_else(|| anyhow!("no container id to stop"))?;

        find_docker().map_err(|_e| {
            anyhow!("Docker is not available; cannot stop the workload container.")
        })?;

        let docker = find_docker().expect("docker was already validated above");
        let now = now_unix_ms();

        record.state = WorkloadLifecycleState::Cancelling;
        record.updated_at_unix_ms = now;

        let output = timeout(Duration::from_secs(15), async {
            Command::new(&docker)
                .args(["stop", container_id])
                .output()
                .await
        })
        .await
        .map_err(|_| anyhow!("timed out while stopping Docker container"))?
        .with_context(|| "failed to stop Docker container")?;

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
            warn!(%container_id, "Docker stop warning: {stderr}");
        }

        let final_now = now_unix_ms();
        record.state = WorkloadLifecycleState::Cancelled;
        record.termination_reason = Some("stopped by user request".into());
        record.updated_at_unix_ms = final_now;

        self.emit(KernelEventRecord::new(
            "workload.stopped",
            "workload",
            &record.workload_id,
            "cancelled",
            &format!("Docker container {} was stopped", &container_id[..12]),
        ));

        Ok(())
    }

    pub async fn collect_logs(&self, record: &WorkloadRecord) -> Result<Vec<(String, String)>> {
        let container_id = record
            .container_id
            .as_ref()
            .ok_or_else(|| anyhow!("no container id for logs"))?;

        find_docker()
            .map_err(|_e| anyhow!("Docker is not available; cannot collect workload logs."))?;

        let docker = find_docker().expect("docker was already validated above");

        let output = timeout(Duration::from_secs(10), async {
            Command::new(&docker)
                .args(["logs", "--tail", "200", container_id])
                .output()
                .await
        })
        .await
        .map_err(|_| anyhow!("timed out while collecting Docker logs"))?
        .with_context(|| "failed to get Docker logs")?;

        let stdout = String::from_utf8_lossy(&output.stdout);
        let stderr = String::from_utf8_lossy(&output.stderr);

        let lines: Vec<(String, String)> = stdout
            .lines()
            .map(|l| (l.to_string(), "stdout".to_string()))
            .chain(
                stderr
                    .lines()
                    .map(|l| (l.to_string(), "stderr".to_string())),
            )
            .collect();

        Ok(lines)
    }
}

fn find_docker() -> Result<PathBuf> {
    let path = std::env::var_os("PATH").ok_or_else(|| anyhow!("PATH not set"))?;

    for dir in std::env::split_paths(&path) {
        let candidate = dir.join("docker");
        if candidate.is_file() {
            return Ok(candidate);
        }
    }

    bail!("docker command not found on PATH; install Docker to use the workload orchestrator")
}
