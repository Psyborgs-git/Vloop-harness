use anyhow::{anyhow, Result};
use dashmap::DashMap;
use std::sync::Arc;
use uuid::Uuid;

use crate::commands::process::{ProcessInfo, ProcessLog};

use super::{manifest::ProcessManifest, supervisor::SupervisedProcess};

pub struct ProcessRegistry {
    processes: Arc<DashMap<String, SupervisedProcess>>,
    app_handle: tauri::AppHandle,
}

impl ProcessRegistry {
    pub fn new(app_handle: tauri::AppHandle) -> Self {
        Self {
            processes: Arc::new(DashMap::new()),
            app_handle,
        }
    }

    pub fn start_process(&self, manifest: ProcessManifest) -> Result<String> {
        let id = Uuid::new_v4().to_string();
        let process = SupervisedProcess::new(
            id.clone(),
            manifest.name,
            manifest.command,
            manifest.args.unwrap_or_default(),
            manifest.cwd,
            manifest.env,
            manifest.port,
            self.app_handle.clone(),
        )?;
        self.processes.insert(id.clone(), process);
        Ok(id)
    }

    pub fn stop_process(&self, id: &str) -> Result<()> {
        let mut entry = self
            .processes
            .get_mut(id)
            .ok_or_else(|| anyhow!("Process not found: {id}"))?;
        entry.stop()
    }

    pub fn restart_process(&self, id: &str) -> Result<()> {
        let manifest = {
            let entry = self
                .processes
                .get(id)
                .ok_or_else(|| anyhow!("Process not found: {id}"))?;
            ProcessManifest {
                name: entry.name.clone(),
                command: entry.command.clone(),
                args: Some(entry.args.clone()),
                cwd: None,
                env: None,
                port: entry.port,
                auto_restart: None,
            }
        };
        self.stop_process(id).ok();
        let new_id = self.start_process(manifest)?;
        tracing::info!("Process {id} restarted as {new_id}");
        Ok(())
    }

    pub fn list_processes(&self) -> Vec<ProcessInfo> {
        self.processes.iter().map(|e| e.to_info()).collect()
    }

    pub fn get_logs(&self, id: &str, limit: usize) -> Result<Vec<ProcessLog>> {
        let entry = self
            .processes
            .get(id)
            .ok_or_else(|| anyhow!("Process not found: {id}"))?;
        Ok(entry.logs(limit))
    }
}
