use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use tauri::State;

use crate::{
    services::fs::{git, vfs, watcher},
    AppState,
};

#[derive(Debug, Serialize, Deserialize)]
pub struct FileEntry {
    pub name: String,
    pub path: String,
    pub is_dir: bool,
    pub size: Option<u64>,
    pub modified: Option<String>,
}

/// Resolve `path` against the configured VFS root, rejecting path-escape attempts.
fn resolve(state: &AppState, path: &str) -> Result<PathBuf, String> {
    vfs::resolve_safe(&state.fs_service.vfs_root, path).map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn fs_list(path: String, state: State<'_, AppState>) -> Result<Vec<FileEntry>, String> {
    let safe_path = resolve(&state, &path)?;
    let entries: Vec<FileEntry> = std::fs::read_dir(&safe_path)
        .map_err(|e| e.to_string())?
        .filter_map(|e| e.ok())
        .map(|e| {
            let meta = e.metadata().ok();
            FileEntry {
                name: e.file_name().to_string_lossy().to_string(),
                path: e.path().to_string_lossy().to_string(),
                is_dir: meta.as_ref().map(|m| m.is_dir()).unwrap_or(false),
                size: meta.as_ref().map(|m| m.len()),
                modified: meta.and_then(|m| m.modified().ok()).map(|t| {
                    chrono::DateTime::<chrono::Utc>::from(t).to_rfc3339()
                }),
            }
        })
        .collect();
    Ok(entries)
}

#[tauri::command]
pub async fn fs_read(path: String, state: State<'_, AppState>) -> Result<String, String> {
    let safe_path = resolve(&state, &path)?;
    std::fs::read_to_string(safe_path).map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn fs_write(
    path: String,
    content: String,
    state: State<'_, AppState>,
) -> Result<(), String> {
    let safe_path = resolve(&state, &path)?;
    if let Some(parent) = safe_path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    std::fs::write(safe_path, content).map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn fs_delete(path: String, state: State<'_, AppState>) -> Result<(), String> {
    let safe_path = resolve(&state, &path)?;
    if safe_path.is_dir() {
        std::fs::remove_dir_all(&safe_path).map_err(|e| e.to_string())
    } else {
        std::fs::remove_file(&safe_path).map_err(|e| e.to_string())
    }
}

#[tauri::command]
pub async fn fs_git_status(
    path: String,
    state: State<'_, AppState>,
) -> Result<git::GitStatus, String> {
    let safe_path = resolve(&state, &path)?;
    git::status(&safe_path.to_string_lossy()).await.map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn fs_git_diff(path: String, state: State<'_, AppState>) -> Result<String, String> {
    let safe_path = resolve(&state, &path)?;
    git::diff(&safe_path.to_string_lossy()).await.map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn fs_git_commit(
    path: String,
    message: String,
    paths: Vec<String>,
    state: State<'_, AppState>,
) -> Result<String, String> {
    let safe_path = resolve(&state, &path)?;
    git::commit(&safe_path.to_string_lossy(), &message, paths)
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn fs_git_branches(
    path: String,
    state: State<'_, AppState>,
) -> Result<Vec<git::GitBranch>, String> {
    let safe_path = resolve(&state, &path)?;
    git::branches(&safe_path.to_string_lossy()).await.map_err(|e| e.to_string())
}

/// Start watching `path` for changes.  Returns a watcher ID that can be passed
/// to `fs_unwatch` to stop watching.  Emits `fs_changed` Tauri events on change.
#[tauri::command]
pub async fn fs_watch(path: String, state: State<'_, AppState>) -> Result<String, String> {
    let safe_path = resolve(&state, &path)?;
    let w = watcher::start_watch(&safe_path, state.fs_service.app_handle.clone())
        .map_err(|e| e.to_string())?;
    let id = w.id.clone();
    state.fs_service.watchers.insert(id.clone(), w);
    Ok(id)
}

/// Stop a previously started watcher.
#[tauri::command]
pub async fn fs_unwatch(watcher_id: String, state: State<'_, AppState>) -> Result<(), String> {
    state
        .fs_service
        .watchers
        .remove(&watcher_id)
        .ok_or_else(|| format!("Watcher not found: {watcher_id}"))?;
    Ok(())
}
