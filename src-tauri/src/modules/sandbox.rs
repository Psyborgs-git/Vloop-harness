use std::process::Command;
use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize, Clone, Debug)]
pub enum SandboxType {
    Local,
    Docker { image: String },
    Ssh { host: String, user: String },
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
            
            if let Some(cwd) = &req.cwd {
                cmd.current_dir(cwd);
            }
            
            // Inject vault variables
            for (k, v) in vault_env.iter() {
                cmd.env(k, v);
            }

            cmd.stdout(std::process::Stdio::from(log_file));
            cmd.stderr(std::process::Stdio::from(log_file_err));

            let child = cmd.spawn().map_err(|e| e.to_string())?;
            Ok(child)
        }
        SandboxType::Docker { image } => {
            let log_file = std::fs::File::create(&log_path).map_err(|e| e.to_string())?;
            let log_file_err = log_file.try_clone().map_err(|e| e.to_string())?;

            let mut args = vec!["run".to_string(), "--rm".to_string()];
            
            // Inject vault variables into docker
            for (k, v) in vault_env.iter() {
                args.push("-e".to_string());
                args.push(format!("{}={}", k, v));
            }
            
            args.push(image);
            args.push(req.command);
            args.extend(req.args);

            let child = Command::new("docker")
                .args(&args)
                .stdout(std::process::Stdio::from(log_file))
                .stderr(std::process::Stdio::from(log_file_err))
                .spawn()
                .map_err(|e| e.to_string())?;

            Ok(child)
        }
        SandboxType::Ssh { host, user } => {
            // Background SSH execution requires different handling.
            // For now, spawn a local SSH command that redirects output to log.
            let log_file = std::fs::File::create(&log_path).map_err(|e| e.to_string())?;
            let log_file_err = log_file.try_clone().map_err(|e| e.to_string())?;

            let mut ssh_args = vec![format!("{}@{}", user, host)];
            
            let mut remote_cmd = String::new();
            for (k, v) in vault_env.iter() {
                remote_cmd.push_str(&format!("export {}='{}'; ", k, v));
            }
            remote_cmd.push_str(&req.command);
            for arg in req.args {
                remote_cmd.push(' ');
                remote_cmd.push_str(&arg);
            }
            ssh_args.push(remote_cmd);

            let child = Command::new("ssh")
                .args(&ssh_args)
                .stdout(std::process::Stdio::from(log_file))
                .stderr(std::process::Stdio::from(log_file_err))
                .spawn()
                .map_err(|e| e.to_string())?;

            Ok(child)
        }
    }
}

#[tauri::command]
pub fn run_in_sandbox(req: SandboxExecutionRequest) -> Result<SandboxExecutionResult, String> {
    // For backwards compatibility where result is expected immediately.
    // We can just call it via Command directly instead of spawn if needed, 
    // or just reimplement a blocking version. For now we will reimplement a simple blocking one.
    
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
        _ => Err("Synchronous run_in_sandbox only supports Local sandbox currently.".to_string()),
    }
}
