pub mod api;
pub mod commands;
pub mod config;
pub mod services;
pub mod telemetry;

use std::sync::Arc;
use tauri::Manager;

use services::{
    db::DbService,
    fs::FsService,
    gateway::GatewayService,
    host::HostService,
    process::ProcessRegistry,
    terminal::TerminalManager,
};

pub struct AppState {
    pub db: Arc<DbService>,
    pub terminal_manager: Arc<TerminalManager>,
    pub fs_service: Arc<FsService>,
    pub process_registry: Arc<ProcessRegistry>,
    pub gateway_service: Arc<GatewayService>,
    pub host_service: Arc<HostService>,
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_process::init())
        .setup(|app| {
            let handle = app.handle().clone();

            // Initialise DB synchronously in a blocking context
            let db = tauri::async_runtime::block_on(async {
                Arc::new(DbService::new().await.expect("Failed to initialise database"))
            });

            let terminal_manager = Arc::new(TerminalManager::new(handle.clone()));
            let fs_service = Arc::new(FsService::new(handle.clone()));
            let process_registry = Arc::new(ProcessRegistry::new(handle.clone()));
            let gateway_service = Arc::new(GatewayService::new(handle.clone()));
            let host_service = Arc::new(HostService::new());

            // Start internal REST API (Rust ↔ Python)
            let db_clone = db.clone();
            tauri::async_runtime::spawn(async move {
                if let Err(e) = api::start_internal_api(db_clone, 47200).await {
                    tracing::error!("Internal API error: {e}");
                }
            });

            app.manage(AppState {
                db,
                terminal_manager,
                fs_service,
                process_registry,
                gateway_service,
                host_service,
            });

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            // DB
            commands::db::db_query,
            commands::db::db_get_agent_runs,
            commands::db::db_get_logs,
            commands::db::db_list_tables,
            commands::db::db_config_get,
            commands::db::db_config_set,
            // Terminal
            commands::terminal::terminal_create,
            commands::terminal::terminal_write,
            commands::terminal::terminal_resize,
            commands::terminal::terminal_kill,
            commands::terminal::terminal_list,
            // FS
            commands::fs::fs_list,
            commands::fs::fs_read,
            commands::fs::fs_write,
            commands::fs::fs_delete,
            commands::fs::fs_git_status,
            commands::fs::fs_git_diff,
            commands::fs::fs_git_commit,
            commands::fs::fs_git_branches,
            // Process
            commands::process::process_start,
            commands::process::process_stop,
            commands::process::process_restart,
            commands::process::process_list,
            commands::process::process_logs,
            // Gateway
            commands::gateway::gateway_list_adapters,
            commands::gateway::gateway_add_adapter,
            commands::gateway::gateway_remove_adapter,
            commands::gateway::gateway_send,
            // Host
            commands::host::host_start,
            commands::host::host_stop,
            commands::host::host_status,
            commands::host::host_rotate_token,
        ])
        .run(tauri::generate_context!())
        .expect("error while running Tauri application");
}
