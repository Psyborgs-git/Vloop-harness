mod completions;
mod config;
mod service;
mod permissions;
mod tools;

use axum::serve;
use clap::{Parser, Subcommand};
use std::sync::{Arc, RwLock, Mutex};
use std::path::PathBuf;
use std::time::Duration;
use std::process::{Command, Stdio};
use tokio::net::TcpListener;

use crate::completions::AppState;
use crate::config::ProviderConfig;
use crate::service::ServiceManager;

#[derive(Parser)]
#[command(name = "vloop-harness", version, about = "Vloop Harness Rust Base")]
struct Cli {
    #[command(subcommand)]
    command: Option<Commands>,
}

#[derive(Subcommand)]
enum Commands {
    /// Start the Vloop Harness orchestrator
    Run {
        #[arg(long, default_value = "127.0.0.1", env = "HARNESS_HOST")]
        host: String,
        #[arg(long, default_value_t = 9100, env = "HARNESS_PORT")]
        port: u16,
        #[arg(long, default_value_t = 9101, env = "HARNESS_AI_PORT")]
        ai_port: u16,
        #[arg(long, help = "Skip opening the native window")]
        no_window: bool,
        #[arg(long, default_value = "dev", help = "Frontend mode ('dev' or 'static')")]
        frontend_mode: String,
    },
    /// Manage harness backend/frontend services
    Services {
        #[command(subcommand)]
        action: ServiceAction,
    },
}

#[derive(Subcommand)]
enum ServiceAction {
    Start {
        #[arg(default_value = "all")]
        target: String,
    },
    Stop {
        #[arg(default_value = "all")]
        target: String,
    },
    Status,
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let cli = Cli::parse();
    let repo_root = get_repo_root();
    let data_dir = get_data_dir(&repo_root);

    if let Err(e) = ensure_python_env(&repo_root, &data_dir) {
        eprintln!("Initialization Error: {}", e);
        std::process::exit(1);
    }

    let is_packaged = repo_root.to_string_lossy().contains("VloopHarness.app")
        || repo_root.to_string_lossy().contains("Resources");
    let default_frontend_mode = if is_packaged { "static" } else { "dev" };

    let command = cli.command.unwrap_or(Commands::Run {
        host: "127.0.0.1".to_string(),
        port: 9100,
        ai_port: 9101,
        no_window: false,
        frontend_mode: default_frontend_mode.to_string(),
    });

    match command {
        Commands::Run {
            host,
            port,
            ai_port,
            no_window,
            frontend_mode,
        } => {
            if no_window {
                let rt = tokio::runtime::Runtime::new()?;
                rt.block_on(async {
                    run_app_headless(repo_root, data_dir, host, port, ai_port, frontend_mode).await
                })?;
            } else {
                let repo_root_clone = repo_root.clone();
                let data_dir_clone = data_dir.clone();
                let host_clone = host.clone();
                let frontend_mode_clone = frontend_mode.clone();

                std::thread::spawn(move || {
                    let rt = tokio::runtime::Runtime::new().unwrap();
                    rt.block_on(async {
                        if let Err(e) = run_app_headless(repo_root_clone, data_dir_clone, host_clone, port, ai_port, frontend_mode_clone).await {
                            eprintln!("App run failed: {}", e);
                        }
                    });
                });

                // Wait 1.5 seconds for the server to spin up
                std::thread::sleep(Duration::from_millis(1500));

                use tao::{
                    event::{Event, WindowEvent},
                    event_loop::{ControlFlow, EventLoop},
                    window::WindowBuilder,
                };
                use wry::WebViewBuilder;

                let event_loop = EventLoop::new();
                let window = WindowBuilder::new()
                    .with_title("Vloop Harness Control Panel")
                    .with_inner_size(tao::dpi::LogicalSize::new(1280.0, 800.0))
                    .build(&event_loop)
                    .unwrap();

                let ui_url = format!("http://{}:{}/ui/root", host, port);
                println!("Opening native window pointing to: {}", ui_url);

                let _webview = WebViewBuilder::new()
                    .with_url(&ui_url)
                    .build(&window)?;

                let repo_root_cleanup = repo_root.clone();
                let data_dir_cleanup = data_dir.clone();
                let host_cleanup = host.clone();
                let frontend_mode_cleanup = frontend_mode.clone();

                event_loop.run(move |event, _, control_flow| {
                    *control_flow = ControlFlow::Wait;
                    match event {
                        Event::WindowEvent {
                            event: WindowEvent::CloseRequested,
                            ..
                        } => {
                            println!("\nWindow closed. Shutting down services...");
                            let stop_manager = ServiceManager::new(
                                repo_root_cleanup.clone(),
                                data_dir_cleanup.clone(),
                                host_cleanup.clone(),
                                port,
                                "127.0.0.1".to_string(),
                                9102,
                                frontend_mode_cleanup.clone(),
                                format!("http://127.0.0.1:{}/v1", ai_port),
                            );
                            let stop_statuses = stop_manager.stop("all");
                            for s in stop_statuses {
                                println!("{:?} - {}", s.name, s.detail);
                            }
                            *control_flow = ControlFlow::Exit;
                        }
                        _ => (),
                    }
                });
            }
        }
        Commands::Services { action } => {
            let rt = tokio::runtime::Runtime::new()?;
            rt.block_on(async {
                let manager = ServiceManager::new(
                    repo_root,
                    data_dir,
                    "127.0.0.1".to_string(),
                    9100,
                    "127.0.0.1".to_string(),
                    9102,
                    default_frontend_mode.to_string(),
                    "http://127.0.0.1:9101/v1".to_string(),
                );
                match action {
                    ServiceAction::Start { target } => {
                        for s in manager.start(&target) {
                            println!("{:10} running: {:5} healthy: {:5} log: {:?}", s.name, s.running, s.healthy, s.log_path);
                        }
                    }
                    ServiceAction::Stop { target } => {
                        for s in manager.stop(&target) {
                            println!("{:10} {}", s.name, s.detail);
                        }
                    }
                    ServiceAction::Status => {
                        for s in manager.status() {
                            println!("{:10} running: {:5} healthy: {:5} {}", s.name, s.running, s.healthy, s.detail);
                        }
                    }
                }
            });
        }
    }

    Ok(())
}

async fn run_app_headless(
    repo_root: PathBuf,
    data_dir: PathBuf,
    host: String,
    port: u16,
    ai_port: u16,
    frontend_mode: String,
) -> Result<(), Box<dyn std::error::Error>> {
    let rust_completions_url = format!("http://127.0.0.1:{}/v1", ai_port);
    let manager = ServiceManager::new(
        repo_root.clone(),
        data_dir.clone(),
        host.clone(),
        port,
        "127.0.0.1".to_string(),
        9102,
        frontend_mode.clone(),
        rust_completions_url,
    );

    println!("Starting Vloop Harness (Rust Base)");

    // 1. Start AI Engine (Axum Server) in background
    let ai_addr = format!("127.0.0.1:{}", ai_port);
    let listener = TcpListener::bind(&ai_addr).await?;
    println!("AI Engine listening on http://{}", ai_addr);

    let permissions = Arc::new(Mutex::new(permissions::PermissionsGuard::new()));
    let tools = Arc::new(tools::ToolsManager::new(repo_root.clone(), data_dir.clone(), permissions.clone()));

    let provider_config = ProviderConfig::from_env();
    let state = AppState {
        provider: Arc::new(RwLock::new(provider_config)),
        client: reqwest::Client::new(),
        tools,
    };
    let app = completions::router(state);

    // Spawn axum server
    tokio::spawn(async move {
        serve(listener, app).await.unwrap();
    });

    // 2. Start subprocesses
    let statuses = manager.start("all");
    for s in statuses {
        println!("{:?} - running: {}", s.name, s.running);
    }

    // Wait for termination signal
    let (tx, rx) = std::sync::mpsc::channel();
    ctrlc::set_handler(move || {
        let _ = tx.send(());
    })?;

    let _ = rx.recv();
    println!("\nShutting down services...");
    let stop_statuses = manager.stop("all");
    for s in stop_statuses {
        println!("{:?} - {}", s.name, s.detail);
    }
    Ok(())
}

fn get_data_dir(repo_root: &std::path::Path) -> PathBuf {
    let app_harness_dir = repo_root.join(".harness");
    let is_bundle = repo_root.to_string_lossy().contains("VloopHarness.app")
        || repo_root.to_string_lossy().contains("Resources");

    if is_bundle {
        if let Some(home) = dirs::home_dir() {
            return home.join(".harness");
        }
    }

    if std::fs::create_dir_all(&app_harness_dir).is_ok() {
        let test_file = app_harness_dir.join(".write_test");
        if std::fs::write(&test_file, "test").is_ok() {
            let _ = std::fs::remove_file(test_file);
            return app_harness_dir;
        }
    }

    if let Some(home) = dirs::home_dir() {
        home.join(".harness")
    } else {
        app_harness_dir
    }
}

fn get_repo_root() -> PathBuf {
    if let Ok(exe_path) = std::env::current_exe() {
        let mut path = exe_path.clone();
        for _ in 0..6 {
            path.pop();
            if path.join("harness").exists() && path.join("pyproject.toml").exists() {
                return path;
            }
            if path.join("Resources").join("harness").exists() && path.join("Resources").join("pyproject.toml").exists() {
                return path.join("Resources");
            }
        }
    }
    std::env::current_dir().unwrap()
}

fn ensure_python_env(repo_root: &std::path::Path, data_dir: &std::path::Path) -> Result<(), String> {
    #[cfg(target_os = "macos")]
    {
        if let Ok(path) = std::env::var("PATH") {
            let new_path = format!("/opt/homebrew/bin:/usr/local/bin:{}", path);
            std::env::set_var("PATH", new_path);
        } else {
            std::env::set_var("PATH", "/opt/homebrew/bin:/usr/local/bin");
        }
    }

    // 1. Check for existing .venv at repo root (dev / pre-installed setup)
    let repo_venv = repo_root.join(".venv");
    if repo_venv.exists() {
        return Ok(());
    }

    // 2. Check for existing .venv in data_dir
    let venv_dir = data_dir.join(".venv");
    if venv_dir.exists() {
        return Ok(());
    }

    println!("Virtual environment (.venv) not found. Setting up in data directory {} using host's Python/uv...", data_dir.display());

    std::fs::create_dir_all(data_dir).ok();

    // 1. Check if uv is installed
    let uv_check = Command::new("uv").arg("--version").output();
    if let Ok(output) = uv_check {
        if output.status.success() {
            println!("Found 'uv' on PATH. Creating virtualenv and syncing dependencies...");
            let venv_status = Command::new("uv")
                .args(&["venv", ".venv"])
                .current_dir(data_dir)
                .stdout(Stdio::inherit())
                .stderr(Stdio::inherit())
                .status();

            if let Ok(s) = venv_status {
                if s.success() {
                    let sync_status = Command::new("uv")
                        .args(&["pip", "install", "-e", &repo_root.to_string_lossy()])
                        .current_dir(data_dir)
                        .stdout(Stdio::inherit())
                        .stderr(Stdio::inherit())
                        .status();

                    match sync_status {
                        Ok(s) if s.success() => {
                            println!("Virtual environment successfully synced with 'uv pip install'.");
                            return Ok(());
                        }
                        _ => return Err("Failed to install package using 'uv pip install'".to_string()),
                    }
                }
            }
        }
    }

    // 2. Fallback: Check if python3/python is available
    let python_cmd = if cfg!(windows) { "python" } else { "python3" };
    let py_check = Command::new(python_cmd).arg("--version").output();
    if let Ok(output) = py_check {
        if output.status.success() {
            println!("Found Python. Creating virtualenv inside data_dir using '{} -m venv'...", python_cmd);
            let venv_status = Command::new(python_cmd)
                .args(&["-m", "venv", ".venv"])
                .current_dir(data_dir)
                .stdout(Stdio::inherit())
                .stderr(Stdio::inherit())
                .status();

            match venv_status {
                Ok(s) if s.success() => {
                    println!("Virtualenv created. Installing dependencies from {}...", repo_root.display());
                    let pip_path = if cfg!(windows) {
                        venv_dir.join("Scripts").join("pip.exe")
                    } else {
                        venv_dir.join("bin").join("pip")
                    };

                    let install_status = Command::new(&pip_path)
                        .args(&["install", "-e", &repo_root.to_string_lossy()])
                        .current_dir(data_dir)
                        .stdout(Stdio::inherit())
                        .stderr(Stdio::inherit())
                        .status();

                    match install_status {
                        Ok(s) if s.success() => {
                            println!("Dependencies successfully installed.");
                            return Ok(());
                        }
                        _ => return Err("Failed to install python dependencies".to_string()),
                    }
                }
                _ => return Err("Failed to create virtualenv using 'python -m venv'".to_string()),
            }
        }
    }

    Err("Neither 'uv' nor 'python'/'python3' was found on the system path. Please install Python and try again.".to_string())
}
