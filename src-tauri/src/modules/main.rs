//! Main module - extracts core functions from original main.rs for Tauri use

use std::fs;
use std::path::PathBuf;
use std::process::{Command, Stdio};

use super::service::ServiceManager;
use super::permissions::PermissionsGuard;
use super::tools::ToolsManager;
use super::completions::AppState;
use super::config::ProviderConfig;

pub fn get_data_dir(repo_root: &std::path::Path) -> PathBuf {
    let app_harness_dir = repo_root.join(".harness");
    let is_bundle = repo_root.to_string_lossy().contains("VloopHarness.app")
        || repo_root.to_string_lossy().contains("Resources");

    if is_bundle {
        if let Some(home) = dirs::home_dir() {
            return home.join(".harness");
        }
    }

    if fs::create_dir_all(&app_harness_dir).is_ok() {
        let test_file = app_harness_dir.join(".write_test");
        if fs::write(&test_file, "test").is_ok() {
            let _ = fs::remove_file(test_file);
            return app_harness_dir;
        }
    }

    if let Some(home) = dirs::home_dir() {
        home.join(".harness")
    } else {
        app_harness_dir
    }
}

pub fn get_repo_root() -> PathBuf {
    if let Ok(exe_path) = std::env::current_exe() {
        let mut path = exe_path.clone();
        for _ in 0..6 {
            path.pop();
            if path.join("harness").exists() && path.join("pyproject.toml").exists() {
                return path;
            }
            if path.join("Resources").join("harness").exists()
                && path.join("Resources").join("pyproject.toml").exists()
            {
                return path.join("Resources");
            }
        }
    }
    std::env::current_dir().unwrap()
}

pub fn ensure_python_env(repo_root: &std::path::Path, data_dir: &std::path::Path) -> Result<(), String> {
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

    fs::create_dir_all(data_dir).ok();

    // 1. Check if uv is installed
    let uv_check = Command::new("uv").arg("--version").output();
    if let Ok(output) = uv_check {
        if output.status.success() {
            println!("Found 'uv' on PATH. Creating virtualenv and syncing dependencies...");
            let venv_status = Command::new("uv")
                .args(["venv", ".venv"])
                .current_dir(data_dir)
                .stdout(Stdio::inherit())
                .stderr(Stdio::inherit())
                .status();

            if let Ok(s) = venv_status {
                if s.success() {
                    let sync_status = Command::new("uv")
                        .args(["pip", "install", "-e", &repo_root.to_string_lossy()])
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
                .args(["-m", "venv", ".venv"])
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
                        .args(["install", "-e", &repo_root.to_string_lossy()])
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

pub async fn run_app_headless(
    repo_root: PathBuf,
    data_dir: PathBuf,
    host: String,
    port: u16,
    ai_port: u16,
    vite_port: u16,
    frontend_mode: String,
) -> Result<(), Box<dyn std::error::Error>> {
    let rust_completions_url = format!("http://127.0.0.1:{}/v1", ai_port);
    let manager = ServiceManager::new(
        repo_root.clone(),
        data_dir.clone(),
        host.clone(),
        port,
        "127.0.0.1".to_string(),
        vite_port,
        frontend_mode.clone(),
        rust_completions_url,
    );

    println!("Starting Vloop Harness (Tauri Backend)");

    // 1. Start AI Engine (Axum Server) in background
    let ai_addr = format!("127.0.0.1:{}", ai_port);
    let listener = tokio::net::TcpListener::bind(&ai_addr).await?;
    println!("AI Engine listening on http://{}", ai_addr);

    let permissions = std::sync::Arc::new(std::sync::Mutex::new(PermissionsGuard::new()));
    let tools = std::sync::Arc::new(ToolsManager::new(repo_root.clone(), data_dir.clone(), permissions.clone()));

    let app_state = AppState {
        provider: std::sync::Arc::new(std::sync::RwLock::new(ProviderConfig::from_env())),
        client: reqwest::Client::new(),
        tools: tools.clone(),
    };

    let ai_server = axum::Router::new()
        .nest("/", super::completions::router())
        .with_state(app_state.clone());

    tokio::spawn(async move {
        if let Err(e) = axum::serve(listener, ai_server).await {
            eprintln!("AI Engine error: {}", e);
        }
    });

    // 2. Start Python backend and frontend
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
