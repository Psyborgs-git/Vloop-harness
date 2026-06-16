//! Main module - extracts core functions from original main.rs for Tauri use

use std::fs;
use std::path::PathBuf;
use std::process::{Command, Stdio};


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

/// Start the Axum-based AI engine and park the async task forever.
///
/// Parameters deliberately kept minimal — port allocation and service
/// lifecycle are owned by the Python `ServiceManager` and `lib.rs`.
pub async fn run_app_headless(
    _repo_root: PathBuf,
    _data_dir: PathBuf,
    _ai_port: u16,
) -> Result<(), Box<dyn std::error::Error>> {
    println!("Starting Vloop Harness (Tauri Backend)");

    // Park this task — the kernel's shutdown path calls stop_all_processes()
    // which terminates everything; this future is dropped at that point.
    std::future::pending::<()>().await;

    Ok(())
}
