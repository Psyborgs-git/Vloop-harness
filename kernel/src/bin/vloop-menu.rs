use std::{
    path::{Path, PathBuf},
    process::{Command, Stdio},
    sync::{Arc, Mutex},
    thread,
    time::Duration,
};
use tao::event_loop::{ControlFlow, EventLoopBuilder};
use tray_icon::{
    menu::{Menu, MenuEvent, MenuItem, PredefinedMenuItem, Submenu},
    TrayIconBuilder,
};
use vloop_kernel::{
    config::{self, VLoopConfig},
    orchestrator::filesystem::RuntimePaths,
    service,
};

#[derive(Debug, Clone)]
struct AppState {
    config: VLoopConfig,
    health: String,
    daemon_running: bool,
}

fn create_vloop_icon() -> tray_icon::Icon {
    // 16x16 icon. We will draw a green circular loop.
    let width = 16;
    let height = 16;
    let mut rgba = vec![0u8; width * height * 4];

    for y in 0..height {
        for x in 0..width {
            let idx = (y * width + x) * 4;
            // Draw a circular loop: distance from center (7.5, 7.5)
            let dx = (x as f32) - 7.5;
            let dy = (y as f32) - 7.5;
            let dist = (dx * dx + dy * dy).sqrt();

            // Draw a loop with radius between 4.5 and 7.5
            if dist >= 4.5 && dist <= 7.5 {
                let edge_softness = 1.0 - (dist - 6.0).abs() / 1.5;
                let alpha = (edge_softness * 255.0).clamp(0.0, 255.0) as u8;
                rgba[idx] = 0;       // R
                rgba[idx + 1] = 200; // G
                rgba[idx + 2] = 100; // B
                rgba[idx + 3] = alpha; // A
            } else if dist < 4.5 {
                // Add a subtle inner dot/circle
                if dist >= 1.5 && dist <= 2.5 {
                    rgba[idx] = 0;
                    rgba[idx + 1] = 160;
                    rgba[idx + 2] = 220; // Cyan-ish blue
                    rgba[idx + 3] = 180;
                }
            }
        }
    }

    tray_icon::Icon::from_rgba(rgba, width as u32, height as u32).unwrap()
}

fn open_path(path: &Path) {
    #[cfg(target_os = "macos")]
    {
        let _ = Command::new("open").arg(path).spawn();
    }
    #[cfg(target_os = "windows")]
    {
        let _ = Command::new("cmd")
            .args(&["/c", "start", "", &path.to_string_lossy()])
            .spawn();
    }
    #[cfg(target_os = "linux")]
    {
        let _ = Command::new("xdg-open").arg(path).spawn();
    }
}

fn run_sibling_command(name: &str, args: &[&str], wait: bool) -> Option<String> {
    let binary = match service::sibling_binary(name) {
        Ok(path) => path,
        Err(_) => return None,
    };

    if !binary.is_file() {
        return None;
    }

    let mut cmd = Command::new(&binary);
    cmd.args(args);

    if wait {
        let output = cmd.output().ok()?;
        Some(String::from_utf8_lossy(&output.stdout).trim().to_string())
    } else {
        cmd.stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .ok();
        None
    }
}

fn query_daemon_status() -> (String, bool) {
    // Check if lock file exists to determine if running
    let paths = match RuntimePaths::detect() {
        Ok(p) => p,
        Err(_) => return ("Stopped".to_string(), false),
    };

    if !paths.lock_file.exists() {
        return ("Stopped".to_string(), false);
    }

    // Read state from kernel-state.json
    if let Ok(content) = std::fs::read_to_string(&paths.state_file) {
        if let Ok(json) = serde_json::from_str::<serde_json::Value>(&content) {
            if let Some(health) = json.get("health").and_then(|h| h.as_str()) {
                let display_health = match health {
                    "starting" => "Starting",
                    "ready" => "Ready (Healthy)",
                    "degraded" => "Degraded",
                    "dependency_missing" => "Dependency Missing",
                    "cp_unregistered" => "Waiting for UI Registration",
                    "cp_restarting" => "UI Restarting",
                    "shutting_down" => "Shutting Down",
                    _ => health,
                };
                return (display_health.to_string(), true);
            }
        }
    }

    ("Running (Unknown State)".to_string(), true)
}

#[derive(Debug)]
enum UserEvent {
    UpdateStatus { health: String, is_running: bool },
}

fn main() {
    // Ensure config is initialized
    let current_config = config::ensure_config_exists().unwrap_or_default();
    config::load_config_to_env();

    let (initial_health, is_running) = query_daemon_status();

    let state = Arc::new(Mutex::new(AppState {
        config: current_config,
        health: initial_health,
        daemon_running: is_running,
    }));

    let event_loop = EventLoopBuilder::<UserEvent>::with_user_event().build();
    let proxy = event_loop.create_proxy();

    // Create main menu
    let tray_menu = Menu::new();

    // 1. Status Section
    let status_text = format!("VLoop Status: {}", state.lock().unwrap().health);
    let status_item = MenuItem::new(&status_text, false, None);

    // 2. Open UI
    let open_ui_item = MenuItem::new("Open VLoop UI", true, None);

    // 3. Daemon Control Submenu
    let control_submenu = Submenu::new("Daemon Controls", true);
    let start_item = MenuItem::new("Start Daemon", !is_running, None);
    let stop_item = MenuItem::new("Stop Daemon", is_running, None);
    let restart_item = MenuItem::new("Restart Daemon", is_running, None);
    control_submenu
        .append_items(&[&start_item, &stop_item, &restart_item])
        .unwrap();

    // 4. Configuration Submenu
    let config_submenu = Submenu::new("Configurations", true);

    let autostart_text = if state.lock().unwrap().config.cp_autostart {
        "CP Autostart: [X] Enabled"
    } else {
        "CP Autostart: [ ] Disabled"
    };
    let toggle_autostart_item = MenuItem::new(autostart_text, true, None);

    // Port selection submenu
    let port_submenu = Submenu::new("HTTP Port", true);
    let port_8765 = MenuItem::new("8765 (Default)", true, None);
    let port_8080 = MenuItem::new("8080", true, None);
    let port_8000 = MenuItem::new("8000", true, None);
    let port_9000 = MenuItem::new("9000", true, None);
    port_submenu
        .append_items(&[&port_8765, &port_8080, &port_8000, &port_9000])
        .unwrap();

    let open_config_file_item = MenuItem::new("Open Configuration File", true, None);
    let open_config_dir_item = MenuItem::new("Open Configuration Folder", true, None);

    config_submenu
        .append_items(&[
            &toggle_autostart_item,
            &port_submenu,
            &PredefinedMenuItem::separator(),
            &open_config_file_item,
            &open_config_dir_item,
        ])
        .unwrap();

    // Update port checkmarks based on active config
    let active_port = state.lock().unwrap().config.cp_http_port;
    port_8765.set_text(if active_port == 8765 { "8765 (Default) [X]" } else { "8765 (Default)" });
    port_8080.set_text(if active_port == 8080 { "8080 [X]" } else { "8080" });
    port_8000.set_text(if active_port == 8000 { "8000 [X]" } else { "8000" });
    port_9000.set_text(if active_port == 9000 { "9000 [X]" } else { "9000" });

    // 5. Diagnostics Submenu
    let diagnostics_submenu = Submenu::new("Diagnostics", true);
    let run_doctor_item = MenuItem::new("Run Doctor Diagnostics", true, None);
    let view_logs_item = MenuItem::new("View Recent Logs", true, None);
    diagnostics_submenu
        .append_items(&[&run_doctor_item, &view_logs_item])
        .unwrap();

    // 6. Quit Item
    let quit_item = MenuItem::new("Quit VLoop Daemon & Tray", true, None);

    tray_menu
        .append_items(&[
            &status_item,
            &PredefinedMenuItem::separator(),
            &open_ui_item,
            &PredefinedMenuItem::separator(),
            &control_submenu,
            &config_submenu,
            &diagnostics_submenu,
            &PredefinedMenuItem::separator(),
            &quit_item,
        ])
        .unwrap();

    let _tray_icon = TrayIconBuilder::new()
        .with_menu(Box::new(tray_menu))
        .with_tooltip("VLoop Control Center")
        .with_icon(create_vloop_icon())
        .build()
        .unwrap();

    // Spawn background thread to poll daemon health and update the menu items
    let state_clone = state.clone();

    thread::spawn(move || loop {
        thread::sleep(Duration::from_millis(1500));
        let (new_health, is_running) = query_daemon_status();

        let mut app_state = state_clone.lock().unwrap();
        if app_state.health != new_health || app_state.daemon_running != is_running {
            app_state.health = new_health.clone();
            app_state.daemon_running = is_running;

            let _ = proxy.send_event(UserEvent::UpdateStatus {
                health: new_health,
                is_running,
            });
        }
    });

    event_loop.run(move |event, _, control_flow| {
        *control_flow = ControlFlow::Wait;

        if let tao::event::Event::NewEvents(tao::event::StartCause::Init) = event {
            // initialization
        }

        if let tao::event::Event::UserEvent(UserEvent::UpdateStatus { health, is_running }) = event {
            status_item.set_text(format!("VLoop Status: {health}"));
            start_item.set_enabled(!is_running);
            stop_item.set_enabled(is_running);
            restart_item.set_enabled(is_running);
        }

        if let Ok(menu_event) = MenuEvent::receiver().try_recv() {
            let id = menu_event.id;

            if id == open_ui_item.id() {
                run_sibling_command("vloop-launcher", &[], false);
            } else if id == start_item.id() {
                run_sibling_command("vloopctl", &["start"], false);
            } else if id == stop_item.id() {
                run_sibling_command("vloopctl", &["stop"], false);
            } else if id == restart_item.id() {
                run_sibling_command("vloopctl", &["restart"], false);
            } else if id == toggle_autostart_item.id() {
                let mut app_state = state.lock().unwrap();
                app_state.config.cp_autostart = !app_state.config.cp_autostart;
                let _ = config::save_config(&app_state.config);
                config::load_config_to_env();

                let autostart_text = if app_state.config.cp_autostart {
                    "CP Autostart: [X] Enabled"
                } else {
                    "CP Autostart: [ ] Disabled"
                };
                toggle_autostart_item.set_text(autostart_text);
            } else if id == port_8765.id() || id == port_8080.id() || id == port_8000.id() || id == port_9000.id() {
                let new_port = if id == port_8765.id() {
                    8765
                } else if id == port_8080.id() {
                    8080
                } else if id == port_8000.id() {
                    8000
                } else {
                    9000
                };

                let mut app_state = state.lock().unwrap();
                app_state.config.cp_http_port = new_port;
                let _ = config::save_config(&app_state.config);
                config::load_config_to_env();

                port_8765.set_text(if new_port == 8765 { "8765 (Default) [X]" } else { "8765 (Default)" });
                port_8080.set_text(if new_port == 8080 { "8080 [X]" } else { "8080" });
                port_8000.set_text(if new_port == 8000 { "8000 [X]" } else { "8000" });
                port_9000.set_text(if new_port == 9000 { "9000 [X]" } else { "9000" });
            } else if id == open_config_file_item.id() {
                if let Some(path) = config::get_config_path() {
                    open_path(&path);
                }
            } else if id == open_config_dir_item.id() {
                if let Some(path) = config::get_config_path().and_then(|p| p.parent().map(|p| p.to_path_buf())) {
                    open_path(&path);
                }
            } else if id == run_doctor_item.id() {
                // Run doctor, save to report, open file
                thread::spawn(|| {
                    if let Some(report) = run_sibling_command("vloopctl", &["doctor"], true) {
                        if let Some(mut path) = config::get_config_path().and_then(|p| p.parent().map(|p| p.to_path_buf())) {
                            path.push("logs");
                            path.push("doctor-report.txt");
                            let _ = std::fs::write(&path, report);
                            open_path(&path);
                        }
                    }
                });
            } else if id == view_logs_item.id() {
                if let Some(mut path) = config::get_config_path().and_then(|p| p.parent().map(|p| p.to_path_buf())) {
                    path.push("logs");
                    open_path(&path);
                }
            } else if id == quit_item.id() {
                // Safely quit daemon
                run_sibling_command("vloopctl", &["stop"], true);
                *control_flow = ControlFlow::Exit;
            }
        }
    });
}
