// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod fs;
mod sys;
mod supervisor;
mod rpc;
mod swarm;
mod litefs_sync;
mod infra;

use crate::rpc::system::system_control_client::SystemControlClient;
use crate::rpc::system::{TaskRequest, WorkflowStateRequest, RewindRequest};
use serde_json::json;

async fn connect_to_python() -> Result<SystemControlClient<tonic::transport::Channel>, String> {
    let vloop_home = fs::get_vloop_home().ok_or_else(|| "Failed to get vloop home".to_string())?;
    let socket_path = vloop_home.join("rust").join("ipc.sock");

    #[cfg(unix)]
    let channel = {
        tonic::transport::Endpoint::try_from("http://[::]:50051")
            .unwrap()
            .connect_with_connector(tower::service_fn(move |_: tonic::transport::Uri| {
                let path = socket_path.clone();
                async move {
                    Ok::<_, std::io::Error>(hyper_util::rt::TokioIo::new(
                        tokio::net::UnixStream::connect(path).await?
                    ))
                }
            }))
            .await
            .map_err(|e| e.to_string())?
    };

    #[cfg(not(unix))]
    let channel = tonic::transport::Endpoint::try_from("http://127.0.0.1:50051")
        .unwrap()
        .connect()
        .await
        .map_err(|e| e.to_string())?;

    Ok(SystemControlClient::new(channel))
}

#[tauri::command]
async fn dispatch_task(task_id: String, objective: String) -> Result<String, String> {
    let mut client = connect_to_python().await?;
    let req = tonic::Request::new(TaskRequest {
        task_id,
        objective,
        max_iterations: 3,
    });
    
    // Dispatch synchronously to keep things simple, or ideally we just trigger and let python run
    // Since Python CP AgentLoop is blocking right now, this call will block.
    // For UI responsiveness, we should dispatch and return, but for MVP blocking is fine 
    // or we spawn a local tokio task to wait for it. Let's spawn it so UI doesn't hang.
    tokio::spawn(async move {
        let _ = client.dispatch_task(req).await;
    });
    
    Ok("Task dispatched to Python Control Plane.".to_string())
}

#[tauri::command]
async fn get_workflow_state(workflow_id: Option<String>) -> Result<String, String> {
    let mut client = connect_to_python().await?;
    let req = tonic::Request::new(WorkflowStateRequest {
        workflow_id: workflow_id.unwrap_or_default(),
    });
    let res = client.get_workflow_state(req).await.map_err(|e| e.to_string())?;
    
    let inner = res.into_inner();
    let json_res = json!({
        "workflow_id": inner.workflow_id,
        "objective": inner.objective,
        "status": inner.status,
        "nodes": inner.nodes.into_iter().map(|n| {
            json!({
                "node_id": n.node_id,
                "name": n.name,
                "status": n.status,
                "dependencies": n.dependencies,
                "payload": n.payload
            })
        }).collect::<Vec<_>>()
    });
    Ok(json_res.to_string())
}

#[tauri::command]
async fn rewind_workflow(workflow_id: String, target_node_id: String) -> Result<String, String> {
    let mut client = connect_to_python().await?;
    let req = tonic::Request::new(RewindRequest {
        workspace_id: workflow_id, // For MVP we map workspace_id to workflow_id
        target_commit_hash: target_node_id, // We use target_commit_hash to pass node_id to the CP
    });
    
    let _ = client.rewind_workspace(req).await.map_err(|e| e.to_string())?;
    Ok("Rewound successfully".to_string())
}

use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, TrayIconBuilder, MouseButtonState, TrayIconEvent};
use tauri::Manager;
use crate::rpc::system::UserActionRequest;

#[tokio::main]
async fn main() {
    println!("VLoop Microkernel Booting...");

    // 1. Probe Memory Limits
    let limits = sys::probe_memory();

    // 2. Initialize VLoop Filesystem boundaries
    let vloop_home = fs::get_vloop_home().expect("Failed to get vloop home");
    let config = fs::ActiveConfig {
        max_memory_bytes: limits.available_for_sandbox,
        data_dir: vloop_home.to_string_lossy().to_string(),
    };

    if let Err(e) = fs::initialize_filesystem(&config) {
        eprintln!("Failed to initialize filesystem: {}", e);
        std::process::exit(1);
    }

    // 3. Pre-flight Check: Sync LiteFS state
    litefs_sync::sync_databases();
    litefs_sync::start_litefs_sync_daemon();

    // 4. Start Python Watchdog in background
    supervisor::start_watchdog();

    // 5. Start Context Daemon (Background RAG) - Handed over to Python
    // context_daemon::start_context_daemon();

    // 6. Start Swarm TCP Listener (P2P Mesh)
    swarm::start_swarm_listener();

    // 7. Boot Tauri System Tray Daemon
    tauri::Builder::default()
        .setup(|app| {
            let quit_i = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
            let cp_i = MenuItem::with_id(app, "open_cp", "Open Control Plane", true, None::<&str>)?;
            let settings_i = MenuItem::with_id(app, "open_settings", "Settings", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&cp_i, &settings_i, &quit_i])?;

            let _tray = TrayIconBuilder::new()
                .menu(&menu)
                .icon(app.default_window_icon().unwrap().clone())
                .on_menu_event(|app, event| {
                    match event.id.as_ref() {
                        "quit" => {
                            // Send Quit action to Python CP
                            let app_handle = app.clone();
                            tokio::spawn(async move {
                                if let Ok(mut client) = connect_to_python().await {
                                    let req = tonic::Request::new(UserActionRequest {
                                        action: "quit".to_string(),
                                    });
                                    let _ = client.notify_user_action(req).await;
                                }
                                app_handle.exit(0);
                            });
                        }
                        "open_cp" => {
                            tokio::spawn(async move {
                                if let Ok(mut client) = connect_to_python().await {
                                    let req = tonic::Request::new(UserActionRequest {
                                        action: "open_home".to_string(),
                                    });
                                    let _ = client.notify_user_action(req).await;
                                }
                            });
                        }
                        "open_settings" => {
                            tokio::spawn(async move {
                                if let Ok(mut client) = connect_to_python().await {
                                    let req = tonic::Request::new(UserActionRequest {
                                        action: "open_settings".to_string(),
                                    });
                                    let _ = client.notify_user_action(req).await;
                                }
                            });
                        }
                        _ => {}
                    }
                })
                .build(app)?;

            println!("Tauri Daemon initialized.");
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|_app_handle, event| match event {
            tauri::RunEvent::ExitRequested { api, .. } => {
                api.prevent_exit();
            }
            _ => {}
        });
}
