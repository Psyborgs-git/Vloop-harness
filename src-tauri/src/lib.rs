// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod modules;

use modules::service::ServiceManager;
use serde::Serialize;
use tauri::{Manager, State};

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
        .invoke_handler(tauri::generate_handler![
            get_harness_config,
            modules::vault::get_vault_key,
            modules::sandbox::run_in_sandbox
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

            let repo_root = repo_root_clone.clone();
            let data_dir = data_dir_clone.clone();
            let frontend_mode = frontend_mode_clone.clone();
            let app_handle = app.handle().clone();

            std::thread::spawn(move || {
                let rt = tokio::runtime::Runtime::new().unwrap();
                rt.block_on(async {
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

            // Wait for backend port to be open before navigating the webview
            let start_time = std::time::Instant::now();
            let timeout = std::time::Duration::from_secs(30);
            while start_time.elapsed() < timeout {
                if std::net::TcpStream::connect(format!("127.0.0.1:{}", backend_port)).is_ok() {
                    break;
                }
                std::thread::sleep(std::time::Duration::from_millis(100));
            }

            // Dynamically navigate main webview window to the correct backend port
            if let Some(main_window) = app.get_webview_window("main") {
                let url_str = format!("http://127.0.0.1:{}/ui/root", backend_port);
                if let Ok(url) = tauri::Url::parse(&url_str) {
                    let _ = main_window.navigate(url);
                }
            }

            let service_manager = ServiceManager::new(
                repo_root_clone,
                data_dir_clone,
                "127.0.0.1".to_string(),
                backend_port,
                "127.0.0.1".to_string(),
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
