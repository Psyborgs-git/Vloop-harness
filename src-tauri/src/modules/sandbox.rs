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
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct SandboxExecutionResult {
    pub stdout: String,
    pub stderr: String,
    pub success: bool,
}

pub fn execute_in_sandbox(req: SandboxExecutionRequest) -> Result<SandboxExecutionResult, String> {
    match req.sandbox {
        SandboxType::Local => {
            let output = Command::new(&req.command)
                .args(&req.args)
                .output()
                .map_err(|e| e.to_string())?;

            Ok(SandboxExecutionResult {
                stdout: String::from_utf8_lossy(&output.stdout).to_string(),
                stderr: String::from_utf8_lossy(&output.stderr).to_string(),
                success: output.status.success(),
            })
        }
        SandboxType::Docker { image } => {
            let mut args = vec!["run".to_string(), "--rm".to_string(), image];
            args.push(req.command);
            args.extend(req.args);

            let output = Command::new("docker")
                .args(&args)
                .output()
                .map_err(|e| e.to_string())?;

            Ok(SandboxExecutionResult {
                stdout: String::from_utf8_lossy(&output.stdout).to_string(),
                stderr: String::from_utf8_lossy(&output.stderr).to_string(),
                success: output.status.success(),
            })
        }
        SandboxType::Ssh { host, user } => {
            use ssh2::Session;
            use std::net::TcpStream;
            use std::io::Read;

            let tcp = TcpStream::connect(format!("{}:22", host)).map_err(|e| e.to_string())?;
            let mut sess = Session::new().map_err(|e| e.to_string())?;
            sess.set_tcp_stream(tcp);
            sess.handshake().map_err(|e| e.to_string())?;

            sess.userauth_agent(&user).map_err(|e| e.to_string())?;

            let mut channel = sess.channel_session().map_err(|e| e.to_string())?;

            let mut full_cmd = req.command.clone();
            for arg in req.args {
                full_cmd.push_str(" ");
                full_cmd.push_str(&arg);
            }

            channel.exec(&full_cmd).map_err(|e| e.to_string())?;

            let mut stdout = String::new();
            channel.read_to_string(&mut stdout).map_err(|e| e.to_string())?;
            let mut stderr = String::new();
            channel.stderr().read_to_string(&mut stderr).map_err(|e| e.to_string())?;

            channel.wait_close().map_err(|e| e.to_string())?;
            let exit_status = channel.exit_status().unwrap_or(1);

            Ok(SandboxExecutionResult {
                stdout,
                stderr,
                success: exit_status == 0,
            })
        }
    }
}

#[tauri::command]
pub fn run_in_sandbox(req: SandboxExecutionRequest) -> Result<SandboxExecutionResult, String> {
    execute_in_sandbox(req)
}
