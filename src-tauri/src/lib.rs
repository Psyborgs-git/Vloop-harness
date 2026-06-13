// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

pub mod modules;

use modules::service::ServiceManager;
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
    #[serde(rename = "initial_state")]
    initial_state: serde_json::Value,
    #[serde(rename = "permissions")]
    permissions: Vec<String>,
}

#[tauri::command]
fn get_harness_config(service_manager: State<ServiceManager>) -> Result<HarnessConfig, String> {
    // Check service health before returning configuration
    if !service_manager.is_backend_running() {
        return Err("Backend service is not running or unhealthy".to_string());
    }

    let host = service_manager.backend_host();
    let port = service_manager.backend_port();

    Ok(HarnessConfig {
        component_id: "root".to_string(),
        api_url: format!("http://{}:{}/api/root", host, port),
        ws_url: format!("ws://{}:{}/ws/root", host, port),
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
async fn test_llm_connection(
    provider_type: String,
    model: String,
    api_key: String,
    base_url: String,
) -> Result<serde_json::Value, String> {
    let client = reqwest::Client::new();
    match provider_type.as_str() {
        "ollama" => {
            let url = if base_url.is_empty() { "http://localhost:11434" } else { &base_url };
            let test_url = format!("{}/api/tags", url.trim_end_matches('/'));
            match client.get(&test_url).timeout(std::time::Duration::from_secs(5)).send().await {
                Ok(res) if res.status().is_success() => {
                    Ok(serde_json::json!({
                        "success": true,
                        "message": format!("Connected to Ollama server at {} successfully!", url)
                    }))
                }
                Ok(res) => {
                    Ok(serde_json::json!({
                        "success": false,
                        "message": format!("Ollama returned status code: {}", res.status())
                    }))
                }
                Err(e) => {
                    Ok(serde_json::json!({
                        "success": false,
                        "message": format!("Failed to reach Ollama server: {}", e)
                    }))
                }
            }
        }
        "anthropic" => {
            let res = client.post("https://api.anthropic.com/v1/messages")
                .header("x-api-key", &api_key)
                .header("anthropic-version", "2023-06-01")
                .json(&serde_json::json!({
                    "model": if model.is_empty() { "claude-3-5-sonnet-20241022" } else { &model },
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1
                }))
                .timeout(std::time::Duration::from_secs(10))
                .send()
                .await;

            match res {
                Ok(response) => {
                    let status = response.status();
                    if status.is_success() {
                        Ok(serde_json::json!({
                            "success": true,
                            "message": "Connection to Anthropic succeeded!"
                        }))
                    } else if status.as_u16() == 401 {
                        Ok(serde_json::json!({
                            "success": false,
                            "message": "Anthropic API key is invalid (Unauthorized 401)."
                        }))
                    } else {
                        let text = response.text().await.unwrap_or_default();
                        Ok(serde_json::json!({
                            "success": false,
                            "message": format!("Anthropic API returned status {}: {}", status, text)
                        }))
                    }
                }
                Err(e) => {
                    Ok(serde_json::json!({
                        "success": false,
                        "message": format!("Failed to reach Anthropic API: {}", e)
                    }))
                }
            }
        }
        "openai" => {
            let url = if base_url.is_empty() { "https://api.openai.com/v1/chat/completions" } else { &base_url };
            let res = client.post(url)
                .header("Authorization", format!("Bearer {}", api_key))
                .json(&serde_json::json!({
                    "model": if model.is_empty() { "gpt-4o" } else { &model },
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1
                }))
                .timeout(std::time::Duration::from_secs(10))
                .send()
                .await;

            match res {
                Ok(response) => {
                    let status = response.status();
                    if status.is_success() {
                        Ok(serde_json::json!({
                            "success": true,
                            "message": "Connection to OpenAI succeeded!"
                        }))
                    } else if status.as_u16() == 401 {
                        Ok(serde_json::json!({
                            "success": false,
                            "message": "OpenAI API key is invalid (Unauthorized 401)."
                        }))
                    } else {
                        let text = response.text().await.unwrap_or_default();
                        Ok(serde_json::json!({
                            "success": false,
                            "message": format!("OpenAI API returned status {}: {}", status, text)
                        }))
                    }
                }
                Err(e) => {
                    Ok(serde_json::json!({
                        "success": false,
                        "message": format!("Failed to reach OpenAI API: {}", e)
                    }))
                }
            }
        }
        _ => {
            Ok(serde_json::json!({
                "success": false,
                "message": format!("Unknown provider type: {}", provider_type)
            }))
        }
    }
}

#[tauri::command]
fn restart_services(service_manager: State<ServiceManager>) -> Result<(), String> {
    println!("Restart requested for Harness services...");
    let _ = service_manager.stop("all");
    let statuses = service_manager.start("all");
    for s in statuses {
        println!("{:?} - running: {}", s.name, s.running);
    }
    Ok(())
}

#[tauri::command]
fn open_settings_window(app_handle: AppHandle) -> Result<(), String> {
    if let Some(window) = app_handle.get_webview_window("settings") {
        let _ = window.set_focus();
        return Ok(());
    }

    let url = tauri::Url::parse("vloop://settings").unwrap();
    let _ = WebviewWindowBuilder::new(&app_handle, "settings", WebviewUrl::CustomProtocol(url))
        .title("Vloop Harness - Kernel Settings")
        .inner_size(580.0, 720.0)
        .resizable(true)
        .build()
        .map_err(|e| format!("Failed to open settings window: {}", e))?;

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

    let is_packaged = repo_root.to_string_lossy().contains("VloopHarness.app")
        || repo_root.to_string_lossy().contains("Resources");
    let frontend_mode = if is_packaged { "static" } else { "dev" };

    let repo_root_clone = repo_root.clone();
    let data_dir_clone = data_dir.clone();
    let frontend_mode_clone = frontend_mode.to_string();

    tauri::Builder::default()
        .plugin(tauri_plugin_log::Builder::new().build())
        .plugin(tauri_plugin_shell::init())
        .register_uri_scheme_protocol("vloop", modules::settings_protocol::handle_vloop_protocol)
        .invoke_handler(tauri::generate_handler![
            get_harness_config,
            modules::vault::get_vault_key,
            modules::sandbox::run_in_sandbox,
            get_settings_config,
            save_settings_config,
            test_llm_connection,
            restart_services,
            open_settings_window
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

            std::thread::spawn(move || {
                let rt = tokio::runtime::Runtime::new().unwrap();
                rt.block_on(async {
                    // Start gRPC server
                    let grpc_addr = format!("127.0.0.1:{}", grpc_port).parse().unwrap();
                    let sandbox_service = modules::sandbox_grpc::MySandboxService::default();
                    let grpc_server = tonic::transport::Server::builder()
                        .add_service(modules::sandbox_grpc::pb::sandbox_service_server::SandboxServiceServer::new(sandbox_service))
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

            // Note: We no longer navigate the main window here. 
            // The rust kernel window remains on vloop://settings as the Command Center.

            let service_manager = ServiceManager::new(
                repo_root_clone,
                data_dir_clone,
                "127.0.0.1".to_string(),
                backend_port,
                vite_port,
                frontend_mode_clone,
                format!("http://127.0.0.1:{}/v1", ai_port),
            );
            app.manage(service_manager);

            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                println!("Window closed. Shutting down services...");
                let manager = window.state::<ServiceManager>();
                let stop_statuses = manager.stop("all");
                for s in stop_statuses {
                    println!("{:?} - {}", s.name, s.detail);
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
