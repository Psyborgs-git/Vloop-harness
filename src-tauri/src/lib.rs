// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

pub mod modules;

use serde::Serialize;
use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use tauri::{
    menu::{Menu, MenuBuilder, MenuItemBuilder, SubmenuBuilder},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Manager, WebviewUrl, WebviewWindowBuilder,
};

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

pub static BACKEND_PORT: once_cell::sync::Lazy<std::sync::Mutex<u16>> =
    once_cell::sync::Lazy::new(|| std::sync::Mutex::new(9100));
pub static GRPC_PORT: once_cell::sync::Lazy<std::sync::Mutex<u16>> =
    once_cell::sync::Lazy::new(|| std::sync::Mutex::new(9105));

#[tauri::command]
fn get_harness_config() -> Result<HarnessConfig, String> {
    let host = "127.0.0.1".to_string();
    let port = *BACKEND_PORT.lock().unwrap();
    let grpc_port = *GRPC_PORT.lock().unwrap();

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
        let _ = window.show();
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

// ── Tray helpers ─────────────────────────────────────────────────────────────

fn show_main_window(app: &AppHandle) {
    // Try to show the named "settings" window (the main UI window label)
    for label in ["settings", "main"] {
        if let Some(w) = app.get_webview_window(label) {
            let _ = w.show();
            let _ = w.set_focus();
            return;
        }
    }
    // If no window exists yet, open a new one
    let _ = open_settings_window(app.clone());
}

fn do_quit(app: &AppHandle, quitting: &Arc<AtomicBool>) {
    if quitting.swap(true, Ordering::SeqCst) {
        return; // Already in the middle of a quit — prevent double-invocation
    }
    println!("[Kernel] Quit requested — stopping all managed processes...");
    crate::modules::process_manager::stop_all_processes();
    println!("[Kernel] Clean shutdown complete.");
    app.exit(0);
}

fn build_tray_menu(app: &AppHandle) -> Result<Menu<tauri::Wry>, tauri::Error> {
    let open_item = MenuItemBuilder::with_id("open", "Open Vloop Harness")
        .build(app)?;
    let separator = tauri::menu::PredefinedMenuItem::separator(app)?;
    let quit_item = MenuItemBuilder::with_id("quit", "Quit Vloop Harness")
        .build(app)?;

    MenuBuilder::new(app)
        .item(&open_item)
        .item(&separator)
        .item(&quit_item)
        .build()
}

// ── macOS native application menu (provides Cmd+Q) ───────────────────────────

#[cfg(target_os = "macos")]
fn build_app_menu(app: &AppHandle) -> Result<Menu<tauri::Wry>, tauri::Error> {
    use tauri::menu::{AboutMetadata, PredefinedMenuItem};

    let app_submenu = SubmenuBuilder::new(app, "Vloop Harness")
        .item(&PredefinedMenuItem::about(
            app,
            Some("About Vloop Harness"),
            Some(AboutMetadata::default()),
        )?)
        .separator()
        .item(&PredefinedMenuItem::services(app, None)?)
        .separator()
        .item(&PredefinedMenuItem::hide(app, None)?)
        .item(&PredefinedMenuItem::hide_others(app, None)?)
        .item(&PredefinedMenuItem::show_all(app, None)?)
        .separator()
        .item(&PredefinedMenuItem::quit(app, Some("Quit Vloop Harness"))?)
        .build()?;

    let window_submenu = SubmenuBuilder::new(app, "Window")
        .item(&PredefinedMenuItem::minimize(app, None)?)
        .item(&PredefinedMenuItem::maximize(app, None)?)
        .item(&PredefinedMenuItem::close_window(app, None)?)
        .build()?;

    MenuBuilder::new(app)
        .item(&app_submenu)
        .item(&window_submenu)
        .build()
}

#[cfg(not(target_os = "macos"))]
fn build_app_menu(app: &AppHandle) -> Result<Menu<tauri::Wry>, tauri::Error> {
    // On Windows/Linux we don't need a global app menu —
    // quit is handled via tray and Alt+F4 (which sends ExitRequested).
    MenuBuilder::new(app).build()
}

// ── Entry point ───────────────────────────────────────────────────────────────

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let repo_root = modules::main::get_repo_root();
    let data_dir = modules::main::get_data_dir(&repo_root);

    if let Err(e) = modules::main::ensure_python_env(&repo_root, &data_dir) {
        eprintln!("Initialization Error: {}", e);
        std::process::exit(1);
    }

    let repo_root_clone = repo_root.clone();
    let data_dir_clone = data_dir.clone();

    // Shared flag: set to true once we've started the shutdown sequence.
    // Prevents double-kill if both a tray Quit and a Cmd+Q fire near-simultaneously.
    let quitting: Arc<AtomicBool> = Arc::new(AtomicBool::new(false));
    let quitting_for_ctrlc = Arc::clone(&quitting);
    // Clone before setup closure consumes it, so run closure can also hold a copy
    let quitting_for_run = Arc::clone(&quitting);

    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            // Second instance launched — bring the existing window to front
            show_main_window(app);
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
            modules::process_manager::get_process_ports,
            modules::process_manager::assign_port,
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
            let grpc_port = modules::health::get_available_port(backend_port + 5);

            {
                if let Ok(mut bp) = BACKEND_PORT.lock() {
                    *bp = backend_port;
                }
                if let Ok(mut gp) = GRPC_PORT.lock() {
                    *gp = grpc_port;
                }
            }

            let repo_root = repo_root_clone.clone();
            let data_dir = data_dir_clone.clone();
            let app_handle = app.handle().clone();

            // ── 1. Databases and core services ───────────────────────────────
            crate::modules::vault::load_vault();
            if let Err(e) = crate::modules::environment::init_db() {
                eprintln!("Failed to initialize environments DB: {}", e);
            }
            if let Err(e) = crate::modules::process_manager::ensure_core_services(&data_dir) {
                eprintln!("Failed to ensure core services: {}", e);
            }
            if let Err(e) = crate::modules::process_manager::update_backend_port(backend_port) {
                eprintln!("Failed to update backend port in DB: {}", e);
            }

            // ── 2. Autostart processes ────────────────────────────────────────
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

            // ── 3. gRPC + AI engine in background thread ─────────────────────
            std::thread::spawn(move || {
                let rt = tokio::runtime::Runtime::new().unwrap();
                rt.block_on(async {
                    let grpc_addr = format!("127.0.0.1:{}", grpc_port).parse().unwrap();
                    let sandbox_service = modules::sandbox_grpc::MySandboxService::default();

                    let process_db_path = data_dir.join("processes.db");
                    let process_service = modules::process_manager_grpc::MyProcessManagerService::new(process_db_path.clone());
                    let environment_service = modules::environment_grpc::MyEnvironmentManagerService::new(process_db_path.clone());
                    let vault_service = modules::vault_grpc::MyVaultService::default();
                    let terminal_service = modules::terminal_grpc::MyTerminalService::default();
                    let system_service = modules::system_grpc::MySystemService::default();
                    let message_bus = Arc::new(modules::message_bus::MessageBus::new());
                    let message_bus_service = modules::message_bus_grpc::MyMessageBusService::new(Arc::clone(&message_bus));

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
                        .add_service(modules::message_bus_grpc::pb::message_bus_service_server::MessageBusServiceServer::new(message_bus_service))
                        .serve(grpc_addr);

                    tokio::spawn(async move {
                        if let Err(e) = grpc_server.await {
                            eprintln!("gRPC server failed: {}", e);
                        }
                    });

                    if let Err(e) = modules::main::run_app_headless(
                        repo_root,
                        data_dir,
                        ai_port,
                    )
                    .await
                    {
                        eprintln!("App run failed: {}", e);
                        let _ = modules::ui::fallback::show_fallback_ui(&app_handle, "App crashed during startup", &e.to_string());
                    }
                });
            });

            // ── 4. Wait for Python backend to be ready ────────────────────────
            let start_time = std::time::Instant::now();
            let timeout = std::time::Duration::from_secs(30);
            while start_time.elapsed() < timeout {
                if std::net::TcpStream::connect(format!("127.0.0.1:{}", backend_port)).is_ok() {
                    break;
                }
                std::thread::sleep(std::time::Duration::from_millis(100));
            }

            // ── 5. macOS native application menu (gives us Cmd+Q) ────────────
            #[cfg(target_os = "macos")]
            {
                if let Ok(menu) = build_app_menu(app.handle()) {
                    let _ = app.set_menu(menu);
                }
            }

            // ── 6. System tray ────────────────────────────────────────────────
            let tray_menu = build_tray_menu(app.handle()).ok();
            let mut tray_builder = TrayIconBuilder::new()
                .tooltip("Vloop Harness");

            // Embed the app icon at compile time (the recommended Tauri v2 approach)
            tray_builder = tray_builder.icon(tauri::include_image!("icons/128x128.png"));

            if let Some(ref menu) = tray_menu {
                tray_builder = tray_builder.menu(menu);
            }

            // Wire tray events
            let quitting_for_tray = Arc::clone(&quitting);
            let tray_built = tray_builder
                .on_menu_event(move |app: &AppHandle, event: tauri::menu::MenuEvent| {
                    match event.id().as_ref() {
                        "open" => show_main_window(app),
                        "quit" => do_quit(app, &quitting_for_tray),
                        _ => {}
                    }
                })
                .on_tray_icon_event(move |tray: &tauri::tray::TrayIcon, event: TrayIconEvent| {
                    // Single left-click on the tray icon → show window
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        show_main_window(tray.app_handle());
                    }
                })
                .build(app);

            if let Err(e) = tray_built {
                // Non-fatal — tray is a convenience, not critical
                eprintln!("[Tray] Failed to build system tray icon: {}", e);
            }

            // ── 7. SIGTERM / Ctrl-C signal handler ────────────────────────────
            let app_handle_for_signal = app.handle().clone();
            let _ = ctrlc::set_handler(move || {
                println!("[Kernel] SIGTERM/SIGINT received — initiating clean shutdown...");
                do_quit(&app_handle_for_signal, &quitting_for_ctrlc);
            });

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run({
            move |app_handle, event| match event {
                // ── Window close button pressed ───────────────────────────────
                // Hide the window rather than quitting the kernel.
                tauri::RunEvent::WindowEvent {
                    label,
                    event: tauri::WindowEvent::CloseRequested { api, .. },
                    ..
                } => {
                    if let Some(window) = app_handle.get_webview_window(&label) {
                        let _ = window.hide();
                    }
                    // Prevent the default close/quit behaviour
                    api.prevent_close();
                    println!("[Kernel] Window '{}' hidden (kernel still running — use tray or Cmd+Q to quit)", label);
                }

                // ── Cmd+Q / native quit menu / tray Quit ─────────────────────
                // ExitRequested fires on macOS Cmd+Q and on app.exit() calls.
                tauri::RunEvent::ExitRequested { api, code, .. } => {
                    // If we haven't started the quit sequence yet this is an OS-initiated
                    // quit (e.g. Cmd+Q). Run our cleanup, then allow the exit.
                    if !quitting_for_run.load(Ordering::SeqCst) {
                        // Only prevent if we haven't already initiated from do_quit()
                        // so we don't get stuck in a loop.
                        quitting_for_run.store(true, Ordering::SeqCst);
                        println!("[Kernel] ExitRequested (code={:?}) — stopping all processes...", code);
                        // Prevent the immediate exit so we can run cleanup synchronously
                        api.prevent_exit();
                        crate::modules::process_manager::stop_all_processes();
                        println!("[Kernel] Clean shutdown complete.");
                        // Now actually exit
                        app_handle.exit(0);
                    }
                    // If quitting is already true, do_quit() already called app.exit(0)
                    // so this is the second fire — just let it through.
                }

                // ── Final exit ────────────────────────────────────────────────
                tauri::RunEvent::Exit => {
                    // Last resort: ensure processes are dead even if ExitRequested was
                    // somehow skipped (e.g. process::exit called externally).
                    if !quitting_for_run.load(Ordering::SeqCst) {
                        crate::modules::process_manager::stop_all_processes();
                    }
                }

                _ => {}
            }
        });
}
