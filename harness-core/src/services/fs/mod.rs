pub mod git;
pub mod vfs;
pub mod watcher;

use std::path::PathBuf;
use std::sync::Arc;

use dashmap::DashMap;
use tauri::AppHandle;

pub struct FsService {
    pub app_handle: AppHandle,
    /// Canonical root for VFS path-escape checks.
    /// Defaults to $HOME (or `/`) and can be overridden via `VLOOP_VFS_ROOT`.
    pub vfs_root: PathBuf,
    /// Active file-system watchers keyed by watcher ID.
    pub watchers: DashMap<String, watcher::FsWatcher>,
}

impl FsService {
    pub fn new(app_handle: AppHandle, vfs_root: PathBuf) -> Self {
        Self {
            app_handle,
            vfs_root,
            watchers: DashMap::new(),
        }
    }
}
