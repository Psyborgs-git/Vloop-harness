use std::process::Command;
use serde::{Deserialize, Serialize};

#[cfg(unix)]
fn configure_process_group(cmd: &mut Command) {
    use std::os::unix::process::CommandExt;
    cmd.process_group(0);
}

#[cfg(not(unix))]
fn configure_process_group(_cmd: &mut Command) {
    // No-op on non-Unix platforms
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub enum SandboxType {
    Local,
    Python { python_path: String },
    Docker { image: String },
    Ssh { host: String, user: String, ssh_key_vault_name: Option<String> },
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct SandboxExecutionRequest {
    pub sandbox: SandboxType,
    pub command: String,
    pub args: Vec<String>,
    pub cwd: Option<String>,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct SandboxExecutionResult {
    pub stdout: String,
    pub stderr: String,
    pub success: bool,
}

pub fn spawn_in_sandbox(req: SandboxExecutionRequest, log_path: std::path::PathBuf) -> Result<std::process::Child, String> {
    let vault_env = crate::modules::vault::get_all_keys();

    // Ensure the parent directory for the log file exists
    if let Some(parent) = log_path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }

    match req.sandbox {
        SandboxType::Local => {
            let log_file = std::fs::File::create(&log_path).map_err(|e| e.to_string())?;
            let log_file_err = log_file.try_clone().map_err(|e| e.to_string())?;

            let mut cmd = Command::new(&req.command);
            cmd.args(&req.args);
            configure_process_group(&mut cmd);
            
            if let Some(cwd) = &req.cwd {
                cmd.current_dir(cwd);
            }
            
            // Inject vault variables
            for (k, v) in vault_env.iter() {
                cmd.env(k, v);
            }

            cmd.stdout(std::process::Stdio::from(log_file));
            cmd.stderr(std::process::Stdio::from(log_file_err));

            let child = cmd.spawn().map_err(|e| {
                if let Ok(mut file) = std::fs::File::create(&log_path) {
                    use std::io::Write;
                    let _ = writeln!(file, "ERROR: Failed to spawn process locally: {}", e);
                }
                e.to_string()
            })?;
            Ok(child)
        }
        SandboxType::Python { python_path } => {
            let log_file = std::fs::File::create(&log_path).map_err(|e| e.to_string())?;
            let log_file_err = log_file.try_clone().map_err(|e| e.to_string())?;

            let mut cmd = Command::new(&req.command);
            cmd.args(&req.args);
            configure_process_group(&mut cmd);
            
            if let Some(cwd) = &req.cwd {
                cmd.current_dir(cwd);
            }

            // Adjust PATH to point to virtual environment's bin/Scripts directory
            let bin_sub = if cfg!(target_os = "windows") { "Scripts" } else { "bin" };
            let virtualenv_bin = std::path::Path::new(&python_path).join(bin_sub);
            
            let current_path = std::env::var("PATH").unwrap_or_default();
            let separator = if cfg!(windows) { ";" } else { ":" };
            let new_path = format!("{}{}{}", virtualenv_bin.to_string_lossy(), separator, current_path);
            
            cmd.env("PATH", new_path);
            cmd.env("VIRTUAL_ENV", &python_path);
            
            // Inject vault variables
            for (k, v) in vault_env.iter() {
                cmd.env(k, v);
            }

            cmd.stdout(std::process::Stdio::from(log_file));
            cmd.stderr(std::process::Stdio::from(log_file_err));

            let child = cmd.spawn().map_err(|e| {
                if let Ok(mut file) = std::fs::File::create(&log_path) {
                    use std::io::Write;
                    let _ = writeln!(file, "ERROR: Failed to spawn Python sandbox: {}", e);
                }
                e.to_string()
            })?;
            Ok(child)
        }
        SandboxType::Docker { image } => {
            let log_file = std::fs::File::create(&log_path).map_err(|e| e.to_string())?;
            let log_file_err = log_file.try_clone().map_err(|e| e.to_string())?;

            let mut args = vec!["run".to_string(), "--rm".to_string()];
            
            if let Some(cwd) = &req.cwd {
                args.push("-w".to_string());
                args.push(cwd.clone());
            }

            // Inject vault variables into docker
            for (k, v) in vault_env.iter() {
                args.push("-e".to_string());
                args.push(format!("{}={}", k, v));
            }
            
            args.push(image);
            args.push(req.command);
            args.extend(req.args);

            let mut cmd = Command::new("docker");
            cmd.args(&args);
            configure_process_group(&mut cmd);

            let child = cmd
                .stdout(std::process::Stdio::from(log_file))
                .stderr(std::process::Stdio::from(log_file_err))
                .spawn()
                .map_err(|e| {
                    if let Ok(mut file) = std::fs::File::create(&log_path) {
                        use std::io::Write;
                        let _ = writeln!(file, "ERROR: Failed to spawn Docker command: {}", e);
                    }
                    e.to_string()
                })?;

            Ok(child)
        }
        SandboxType::Ssh { host, user, ssh_key_vault_name } => {
            let log_file = std::fs::File::create(&log_path).map_err(|e| e.to_string())?;
            let log_file_err = log_file.try_clone().map_err(|e| e.to_string())?;

            let mut ssh_args = Vec::new();
            
            // If there's a key in the vault, retrieve and save to a secure local file for SSH
            let mut key_file_path = None;
            if let Some(ref vault_name) = ssh_key_vault_name {
                if let Some(key_content) = crate::modules::vault::get_key(vault_name) {
                    let repo_root = crate::modules::main::get_repo_root();
                    let data_dir = crate::modules::main::get_data_dir(&repo_root);
                    let keys_dir = data_dir.join("ssh_keys");
                    let _ = std::fs::create_dir_all(&keys_dir);
                    
                    let key_path = keys_dir.join(format!("{}.key", vault_name));
                    if let Ok(_) = std::fs::write(&key_path, &key_content) {
                        #[cfg(unix)]
                        {
                            use std::os::unix::fs::PermissionsExt;
                            let mut perms = std::fs::metadata(&key_path).unwrap().permissions();
                            perms.set_mode(0o600);
                            let _ = std::fs::set_permissions(&key_path, perms);
                        }
                        key_file_path = Some(key_path);
                    }
                }
            }

            if let Some(ref path) = key_file_path {
                ssh_args.push("-i".to_string());
                ssh_args.push(path.to_string_lossy().to_string());
            }
            
            // Prevent hanging in background tasks
            ssh_args.push("-o".to_string());
            ssh_args.push("StrictHostKeyChecking=no".to_string());
            ssh_args.push("-o".to_string());
            ssh_args.push("UserKnownHostsFile=/dev/null".to_string());

            ssh_args.push(format!("{}@{}", user, host));

            let mut remote_cmd = String::new();
            if let Some(cwd) = &req.cwd {
                remote_cmd.push_str(&format!("cd {} && ", cwd));
            }
            
            for (k, v) in vault_env.iter() {
                remote_cmd.push_str(&format!("export {}='{}'; ", k, v));
            }
            remote_cmd.push_str(&req.command);
            for arg in req.args {
                remote_cmd.push(' ');
                remote_cmd.push_str(&arg);
            }
            ssh_args.push(remote_cmd);

            let mut cmd = Command::new("ssh");
            cmd.args(&ssh_args);
            configure_process_group(&mut cmd);

            let child = cmd
                .stdout(std::process::Stdio::from(log_file))
                .stderr(std::process::Stdio::from(log_file_err))
                .spawn()
                .map_err(|e| {
                    if let Ok(mut file) = std::fs::File::create(&log_path) {
                        use std::io::Write;
                        let _ = writeln!(file, "ERROR: Failed to spawn SSH command: {}", e);
                    }
                    e.to_string()
                })?;

            Ok(child)
        }
    }
}

#[tauri::command]
pub fn run_in_sandbox(req: SandboxExecutionRequest) -> Result<SandboxExecutionResult, String> {
    let vault_env = crate::modules::vault::get_all_keys();

    match req.sandbox {
        SandboxType::Local => {
            let mut cmd = Command::new(&req.command);
            cmd.args(&req.args);
            if let Some(cwd) = &req.cwd {
                cmd.current_dir(cwd);
            }
            for (k, v) in vault_env.iter() { cmd.env(k, v); }
            let output = cmd.output().map_err(|e| e.to_string())?;
            Ok(SandboxExecutionResult {
                stdout: String::from_utf8_lossy(&output.stdout).to_string(),
                stderr: String::from_utf8_lossy(&output.stderr).to_string(),
                success: output.status.success(),
            })
        }
        SandboxType::Python { python_path } => {
            let mut cmd = Command::new(&req.command);
            cmd.args(&req.args);
            if let Some(cwd) = &req.cwd {
                cmd.current_dir(cwd);
            }
            
            let bin_sub = if cfg!(target_os = "windows") { "Scripts" } else { "bin" };
            let virtualenv_bin = std::path::Path::new(&python_path).join(bin_sub);
            let current_path = std::env::var("PATH").unwrap_or_default();
            let separator = if cfg!(windows) { ";" } else { ":" };
            let new_path = format!("{}{}{}", virtualenv_bin.to_string_lossy(), separator, current_path);
            
            cmd.env("PATH", new_path);
            cmd.env("VIRTUAL_ENV", &python_path);

            for (k, v) in vault_env.iter() { cmd.env(k, v); }
            let output = cmd.output().map_err(|e| e.to_string())?;
            Ok(SandboxExecutionResult {
                stdout: String::from_utf8_lossy(&output.stdout).to_string(),
                stderr: String::from_utf8_lossy(&output.stderr).to_string(),
                success: output.status.success(),
            })
        }
        _ => Err("Synchronous run_in_sandbox only supports Local and Python sandboxes currently.".to_string()),
    }
}
