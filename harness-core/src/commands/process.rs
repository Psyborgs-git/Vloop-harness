use serde::{Deserialize, Serialize};
use tauri::State;

use crate::{
    services::process::manifest::ProcessManifest,
    AppState,
};

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct ProcessInfo {
    pub id: String,
    pub name: String,
    pub command: String,
    pub status: String,
    pub pid: Option<u32>,
    pub port: Option<u16>,
    pub started_at: Option<String>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct ProcessLog {
    pub process_id: String,
    pub stream: String,
    pub line: String,
    pub ts: String,
}

#[tauri::command]
pub async fn process_start(
    manifest: ProcessManifest,
    state: State<'_, AppState>,
) -> Result<String, String> {
    state
        .process_registry
        .start_process(manifest)
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn process_stop(id: String, state: State<'_, AppState>) -> Result<(), String> {
    state
        .process_registry
        .stop_process(&id)
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn process_restart(id: String, state: State<'_, AppState>) -> Result<(), String> {
    state
        .process_registry
        .restart_process(&id)
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn process_list(state: State<'_, AppState>) -> Result<Vec<ProcessInfo>, String> {
    Ok(state.process_registry.list_processes())
}

#[tauri::command]
pub async fn process_logs(
    id: String,
    limit: Option<usize>,
    state: State<'_, AppState>,
) -> Result<Vec<ProcessLog>, String> {
    state
        .process_registry
        .get_logs(&id, limit.unwrap_or(200))
        .map_err(|e| e.to_string())
}
