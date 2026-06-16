// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

pub mod modules;

use serde::Serialize;
use std::collections::HashMap;
use tauri::{AppHandle, Manager, State, WebviewUrl, WebviewWindowBuilder};

#[derive(Serialize)]
struct HarnessConfig {
    #[serde(rename = "component_id")]
    component_id: String,
    #[serde(rename = "api_url")]
    api_url: String,
    #[serde(rename = "ws_url")]
    ws_url: String,
    #[serde(rename = "grpc_port")]
    grpc_port: u16,
    #[serde(rename = "initial_state")]
    initial_state: serde_json::Value,
    #[serde(rename = "permissions")]
    permissions: Vec<String>,
}

#[tauri::command]
fn get_harness_config() -> Result<HarnessConfig, String> {
    // Return base configuration
    let host = "127.0.0.1".to_string();
    let port = 9100;
    
    // Attempt to guess dynamic grpc_port, or fallback
    let grpc_port = port + 2;

    Ok(HarnessConfig {
        component_id: "root".to_string(),
        api_url: format!("http://{}:{}/api/root", host, port),
        ws_url: format!("ws://{}:{}/ws/root", host, port),
        grpc_port,
        initial_state: serde_json::Value::Object(serde_json::Map::new()),
        permissions: vec![],
    })
}

#[tauri::command]
fn get_settings_config() -> Result<serde_json::Value, String> {
    let repo_root = modules::main::get_repo_root();
    let vars = modules::settings_protocol::read_env_vars(&repo_root);
    
    let mut map = serde_json::Map::new();
    for (k, v) in vars {
        map.insert(k, serde_json::Value::String(v));
    }
    Ok(serde_json::Value::Object(map))
}

#[tauri::command]
fn save_settings_config(config: HashMap<String, String>) -> Result<(), String> {
    let repo_root = modules::main::get_repo_root();
    modules::settings_protocol::update_env_file(&repo_root, &config)
}

#[tauri::command]
fn restart_services() -> Result<(), String> {
    println!("Restart requested for Harness services...");
    if let Ok(processes) = crate::modules::process_manager::list_processes() {
        for p in processes {
            if p.status == "running" {
                let _ = crate::modules::process_manager::stop_process(p.id.clone());
                let _ = crate::modules::process_manager::start_process(p.id);
            }
        }
    }
    Ok(())
}

#[tauri::command]
fn open_settings_window(app_handle: AppHandle) -> Result<(), String> {
    if let Some(window) = app_handle.get_webview_window("settings") {
        let _ = window.set_focus();
        return Ok(());
    }

    let url = WebviewUrl::App("control-pane.html".into());

    let _ = WebviewWindowBuilder::new(&app_handle, "settings", url)
        .title("Vloop Command Center")
        .inner_size(900.0, 720.0)
        .resizable(true)
        .build()
        .map_err(|e| format!("Failed to open command center window: {}", e))?;

    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let repo_root = modules::main::get_repo_root();
    let data_dir = modules::main::get_data_dir(&repo_root);

    if let Err(e) = modules::main::ensure_python_env(&repo_root, &data_dir) {
        eprintln!("Initialization Error: {}", e);
        std::process::exit(1);
    }

    let frontend_mode = "static";

    let repo_root_clone = repo_root.clone();
    let data_dir_clone = data_dir.clone();
    let frontend_mode_clone = frontend_mode.to_string();

    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            let _ = app.get_webview_window("settings").map(|w| {
                let _ = w.set_focus();
            });
        }))
        .plugin(tauri_plugin_log::Builder::new().build())
        .plugin(tauri_plugin_shell::init())
        .register_uri_scheme_protocol("vloop", modules::settings_protocol::handle_vloop_protocol)
        .invoke_handler(tauri::generate_handler![
            get_harness_config,
            modules::vault::get_vault_key,
            modules::sandbox::run_in_sandbox,
            get_settings_config,
            save_settings_config,
            restart_services,
            open_settings_window,
            modules::process_manager::list_processes,
            modules::process_manager::get_process,
            modules::process_manager::create_process,
            modules::process_manager::update_process,
            modules::process_manager::delete_process,
            modules::process_manager::start_process,
            modules::process_manager::stop_process,
            modules::process_manager::read_process_logs,
            modules::environment::list_environments,
            modules::environment::get_environment,
            modules::environment::create_environment,
            modules::environment::update_environment,
            modules::environment::delete_environment
        ])
        .setup(move |app| {
            let health_report = modules::health::check_system_health(&repo_root_clone, &data_dir_clone);

            if !health_report.python_ok || !health_report.node_ok || !health_report.db_accessible {
                let logs = "Boot failed during health check.";
                let _ = modules::ui::fallback::show_fallback_ui(app.handle(), logs, &health_report.details);
                return Ok(());
            }

            let backend_port = modules::health::get_available_port(9100);
            let ai_port = modules::health::get_available_port(backend_port + 1);
            let vite_port = modules::health::get_available_port(5173);
            let grpc_port = modules::health::get_available_port(backend_port + 2);

            let repo_root = repo_root_clone.clone();
            let data_dir = data_dir_clone.clone();
            let frontend_mode = frontend_mode_clone.clone();
            let app_handle = app.handle().clone();

            // 1. Initialize databases and core services
            if let Err(e) = crate::modules::environment::init_db() {
                eprintln!("Failed to initialize environments DB: {}", e);
            }
            if let Err(e) = crate::modules::process_manager::ensure_core_services(&data_dir) {
                eprintln!("Failed to ensure core services: {}", e);
            }

            // 2. Start any process marked as autostart
            if let Ok(processes) = crate::modules::process_manager::list_processes() {
                for p in processes {
                    if p.config.autostart {
                        println!("Auto-starting process: {}", p.name);
                        if let Err(e) = crate::modules::process_manager::start_process(p.id.clone()) {
                            eprintln!("Failed to auto-start {}: {}", p.name, e);
                        }
                    }
                }
            }

            std::thread::spawn(move || {
                let rt = tokio::runtime::Runtime::new().unwrap();
                rt.block_on(async {
                    // Start gRPC server
                    let grpc_addr = format!("127.0.0.1:{}", grpc_port).parse().unwrap();
                    let sandbox_service = modules::sandbox_grpc::MySandboxService::default();
                    
                    let process_db_path = data_dir.join("processes.db");
                    let process_service = modules::process_manager_grpc::MyProcessManagerService::new(process_db_path.clone());
                    let environment_service = modules::environment_grpc::MyEnvironmentManagerService::new(process_db_path.clone());

                    let vault_service = modules::vault_grpc::MyVaultService::default();
                    let terminal_service = modules::terminal_grpc::MyTerminalService::default();
                    let system_service = modules::system_grpc::MySystemService::default();

                    let grpc_server = tonic::transport::Server::builder()
                        .accept_http1(true)
                        .layer(tower_http::cors::CorsLayer::permissive())
                        .layer(tonic_web::GrpcWebLayer::new())
                        .add_service(modules::sandbox_grpc::pb::sandbox_service_server::SandboxServiceServer::new(sandbox_service))
                        .add_service(modules::process_manager_grpc::pb::process_manager_service_server::ProcessManagerServiceServer::new(process_service))
                        .add_service(modules::environment_grpc::pb::environment_manager_service_server::EnvironmentManagerServiceServer::new(environment_service))
                        .add_service(modules::vault_grpc::pb::vault_service_server::VaultServiceServer::new(vault_service))
                        .add_service(modules::terminal_grpc::pb::terminal_service_server::TerminalServiceServer::new(terminal_service))
                        .add_service(modules::system_grpc::pb::system_service_server::SystemServiceServer::new(system_service))
                        .serve(grpc_addr);
                    
                    tokio::spawn(async move {
                        if let Err(e) = grpc_server.await {
                            eprintln!("gRPC server failed: {}", e);
                        }
                    });

                    if let Err(e) = modules::main::run_app_headless(
                        repo_root,
                        data_dir,
                        "127.0.0.1".to_string(),
                        backend_port,
                        ai_port,
                        vite_port,
                        grpc_port,
                        frontend_mode,
                    )
                    .await
                    {
                        eprintln!("App run failed: {}", e);
                        let _ = modules::ui::fallback::show_fallback_ui(&app_handle, "App crashed during startup", &e.to_string());
                    }
                });
            });

            // Wait for backend port to be open to ensure Python orchestrator is ready
            let start_time = std::time::Instant::now();
            let timeout = std::time::Duration::from_secs(30);
            while start_time.elapsed() < timeout {
                if std::net::TcpStream::connect(format!("127.0.0.1:{}", backend_port)).is_ok() {
                    break;
                }
                std::thread::sleep(std::time::Duration::from_millis(100));
            }

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|_app_handle, event| {
            if let tauri::RunEvent::Exit = event {
                println!("App exiting. Shutting down services...");
                if let Ok(processes) = crate::modules::process_manager::list_processes() {
                    for p in processes {
                        if p.status == "running" {
                            let _ = crate::modules::process_manager::stop_process(p.id);
                        }
                    }
                }
            }
        });
}
