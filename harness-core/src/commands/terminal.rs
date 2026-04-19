use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use tauri::State;

use crate::AppState;

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct TerminalSessionInfo {
    pub id: String,
    pub shell: String,
    pub cwd: String,
    pub pid: Option<u32>,
    pub status: String,
}

#[tauri::command]
pub async fn terminal_create(
    shell: Option<String>,
    cwd: Option<String>,
    state: State<'_, AppState>,
) -> Result<String, String> {
    let shell = shell.unwrap_or_else(default_shell);
    let cwd = cwd.unwrap_or_else(|| std::env::current_dir()
        .unwrap_or_default()
        .to_string_lossy()
        .to_string());
    state
        .terminal_manager
        .create_session(shell, cwd, HashMap::new())
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn terminal_write(
    session_id: String,
    data: String,
    state: State<'_, AppState>,
) -> Result<(), String> {
    state
        .terminal_manager
        .write_to_session(&session_id, data.as_bytes())
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn terminal_resize(
    session_id: String,
    cols: u16,
    rows: u16,
    state: State<'_, AppState>,
) -> Result<(), String> {
    state
        .terminal_manager
        .resize_session(&session_id, cols, rows)
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn terminal_kill(
    session_id: String,
    state: State<'_, AppState>,
) -> Result<(), String> {
    state
        .terminal_manager
        .kill_session(&session_id)
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn terminal_list(
    state: State<'_, AppState>,
) -> Result<Vec<TerminalSessionInfo>, String> {
    Ok(state.terminal_manager.list_sessions())
}

fn default_shell() -> String {
    #[cfg(target_os = "windows")]
    return "cmd.exe".to_string();
    #[cfg(target_os = "macos")]
    return std::env::var("SHELL").unwrap_or_else(|_| "/bin/zsh".to_string());
    #[cfg(not(any(target_os = "windows", target_os = "macos")))]
    return std::env::var("SHELL").unwrap_or_else(|_| "/bin/bash".to_string());
}
