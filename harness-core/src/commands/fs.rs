use serde::{Deserialize, Serialize};
use std::path::Path;
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

#[tauri::command]
pub async fn fs_list(path: String) -> Result<Vec<FileEntry>, String> {
    let p = Path::new(&path);
    let entries: Vec<FileEntry> = std::fs::read_dir(p)
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
pub async fn fs_read(path: String) -> Result<String, String> {
    std::fs::read_to_string(&path).map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn fs_write(path: String, content: String) -> Result<(), String> {
    std::fs::write(&path, content).map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn fs_delete(path: String) -> Result<(), String> {
    let p = Path::new(&path);
    if p.is_dir() {
        std::fs::remove_dir_all(&path).map_err(|e| e.to_string())
    } else {
        std::fs::remove_file(&path).map_err(|e| e.to_string())
    }
}

#[tauri::command]
pub async fn fs_git_status(path: String) -> Result<git::GitStatus, String> {
    git::status(&path).await.map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn fs_git_diff(path: String) -> Result<String, String> {
    git::diff(&path).await.map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn fs_git_commit(
    path: String,
    message: String,
    paths: Vec<String>,
) -> Result<String, String> {
    git::commit(&path, &message, paths)
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn fs_git_branches(path: String) -> Result<Vec<git::GitBranch>, String> {
    git::branches(&path).await.map_err(|e| e.to_string())
}
