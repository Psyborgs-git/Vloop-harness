pub mod git;
pub mod vfs;
pub mod watcher;

use std::sync::Arc;
use tauri::AppHandle;

pub struct FsService {
    pub app_handle: AppHandle,
}

impl FsService {
    pub fn new(app_handle: AppHandle) -> Self {
        Self { app_handle }
    }
}
