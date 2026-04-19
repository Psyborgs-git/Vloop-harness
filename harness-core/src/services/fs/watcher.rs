use anyhow::{anyhow, Result};
use notify::{recommended_watcher, EventKind, RecursiveMode, Watcher};
use std::{
    path::Path,
    sync::{Arc, Mutex},
    time::Duration,
};
use tauri::Emitter;
use uuid::Uuid;

pub struct FsWatcher {
    pub id: String,
    _watcher: notify::RecommendedWatcher,
}

pub fn start_watch(path: &Path, app_handle: tauri::AppHandle) -> Result<FsWatcher> {
    let id = Uuid::new_v4().to_string();
    let id_clone = id.clone();
    let path_str = path.to_string_lossy().to_string();

    let mut watcher = recommended_watcher(move |res: notify::Result<notify::Event>| {
        if let Ok(event) = res {
            let kind = match event.kind {
                EventKind::Create(_) => "create",
                EventKind::Modify(_) => "modify",
                EventKind::Remove(_) => "remove",
                _ => "other",
            };
            for p in &event.paths {
                let _ = app_handle.emit(
                    "fs_changed",
                    serde_json::json!({
                        "watcher_id": id_clone,
                        "path": p.to_string_lossy(),
                        "kind": kind,
                    }),
                );
            }
        }
    })
    .map_err(|e| anyhow!("Watcher error: {e}"))?;

    watcher
        .watch(path, RecursiveMode::Recursive)
        .map_err(|e| anyhow!("Watch error: {e}"))?;

    Ok(FsWatcher { id, _watcher: watcher })
}
