use serde::{Deserialize, Serialize};
use std::fs::{self, File};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::thread;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

#[derive(Serialize, Deserialize, Debug)]
struct PidData {
    pid: u32,
    command: Vec<String>,
    cwd: String,
    started_at: f64,
}

#[derive(Debug)]
#[allow(dead_code)]
pub struct ServiceStatus {
    pub name: String,
    pub running: bool,
    pub healthy: bool,
    pub log_path: PathBuf,
    pub detail: String,
}

pub struct ServiceManager {
    repo_root: PathBuf,
    log_dir: PathBuf,
    service_dir: PathBuf,
    backend_host: String,
    backend_port: u16,
    vite_host: String,
    vite_port: u16,
    frontend_mode: String,
    rust_completions_url: String,
}

impl ServiceManager {
    pub fn new(
        repo_root: PathBuf,
        data_dir: PathBuf,
        backend_host: String,
        backend_port: u16,
        vite_host: String,
        vite_port: u16,
        frontend_mode: String,
        rust_completions_url: String,
    ) -> Self {
        let log_dir = data_dir.join("logs");
        let service_dir = log_dir.join("services");
        fs::create_dir_all(&service_dir).ok();

        Self {
            repo_root,
            log_dir,
            service_dir,
            backend_host,
            backend_port,
            vite_host,
            vite_port,
            frontend_mode,
            rust_completions_url,
        }
    }

    pub fn start(&self, target: &str) -> Vec<ServiceStatus> {
        let targets = self.expand_target(target);
        let mut statuses = Vec::new();
        for name in targets {
            if name == "backend" {
                statuses.push(self.start_backend());
            } else if name == "frontend" {
                statuses.push(self.start_frontend());
            }
        }
        statuses
    }

    pub fn stop(&self, target: &str) -> Vec<ServiceStatus> {
        let targets = self.expand_target(target);
        let mut statuses = Vec::new();
        for name in targets {
            statuses.push(self.stop_service(&name));
        }
        statuses
    }

    #[allow(dead_code)]
    pub fn status(&self) -> Vec<ServiceStatus> {
        let mut statuses = Vec::new();
        for name in &["backend", "frontend"] {
            if *name == "frontend" && self.frontend_mode == "static" {
                statuses.push(ServiceStatus {
                    name: "frontend".to_string(),
                    running: true,
                    healthy: true,
                    log_path: self.service_log("frontend"),
                    detail: "static mode (served by backend)".to_string(),
                });
                continue;
            }
            statuses.push(self.status_for(name));
        }
        statuses
    }

    // Configuration getters for Tauri commands
    pub fn backend_host(&self) -> &str {
        &self.backend_host
    }

    pub fn backend_port(&self) -> u16 {
        self.backend_port
    }

    pub fn is_backend_running(&self) -> bool {
        let status = self.status_for("backend");
        status.running && status.healthy
    }

    fn start_backend(&self) -> ServiceStatus {
        let mut status = self.status_for("backend");
        if status.running && status.healthy {
            status.detail = format!("already running on http://{}:{}", self.backend_host, self.backend_port);
            return status;
        }

        // 1. Prefer an existing .venv at the repo root (dev setup)
        let mut python_path: Option<PathBuf> = None;
        let repo_venv = self.repo_root.join(".venv");
        if repo_venv.exists() {
            let candidate = if cfg!(windows) {
                repo_venv.join("Scripts").join("python.exe")
            } else {
                repo_venv.join("bin").join("python")
            };
            if candidate.exists() {
                python_path = Some(candidate);
            }
        }

        // 2. Fallback to .venv inside data_dir
        if python_path.is_none() {
            let data_venv = self.log_dir.parent().unwrap().join(".venv");
            if data_venv.exists() {
                let candidate = if cfg!(windows) {
                    data_venv.join("Scripts").join("python.exe")
                } else {
                    data_venv.join("bin").join("python")
                };
                if candidate.exists() {
                    python_path = Some(candidate);
                }
            }
        }

        let cmd = if let Some(py) = python_path {
            vec![
                py.to_string_lossy().to_string(),
                "-m".to_string(),
                "harness.main".to_string(),
                "internal".to_string(),
                "backend-worker".to_string(),
                "--host".to_string(),
                self.backend_host.clone(),
                "--port".to_string(),
                self.backend_port.to_string(),
            ]
        } else {
            // 3. No venv found — try uv run (creates ephemeral env from pyproject.toml)
            let has_uv = Command::new("uv")
                .arg("--version")
                .output()
                .map(|o| o.status.success())
                .unwrap_or(false);

            if has_uv {
                vec![
                    "uv".to_string(),
                    "run".to_string(),
                    "python".to_string(),
                    "-m".to_string(),
                    "harness.main".to_string(),
                    "internal".to_string(),
                    "backend-worker".to_string(),
                    "--host".to_string(),
                    self.backend_host.clone(),
                    "--port".to_string(),
                    self.backend_port.to_string(),
                ]
            } else {
                // 4. Final fallback: system python3
                let python_cmd = if cfg!(windows) { "python" } else { "python3" };
                vec![
                    python_cmd.to_string(),
                    "-m".to_string(),
                    "harness.main".to_string(),
                    "internal".to_string(),
                    "backend-worker".to_string(),
                    "--host".to_string(),
                    self.backend_host.clone(),
                    "--port".to_string(),
                    self.backend_port.to_string(),
                ]
            }
        };

        let harness_debug = if self.frontend_mode == "static" { "false" } else { "true" };
        let state_db_path = self.log_dir.parent().unwrap().join("state.db").to_string_lossy().to_string();
        let log_dir_str = self.log_dir.to_string_lossy().to_string();
        let cache_dir_str = self.log_dir.parent().unwrap().join("dspy_cache").to_string_lossy().to_string();
        let envs = vec![
            ("HARNESS_DEBUG", harness_debug),
            ("RUST_BASE_AI_URL", &self.rust_completions_url),
            ("STATE_DB_PATH", &state_db_path),
            ("LOG_DIR", &log_dir_str),
            ("CACHE_DIR", &cache_dir_str),
        ];

        let proc_pid = self.spawn_service("backend", &cmd, &self.repo_root, envs);
        if !self.wait_for_port(&self.backend_host, self.backend_port, 120.0, 0.3) {
            self.terminate_pid(proc_pid);
            panic!("Backend failed to start on port {}", self.backend_port);
        }

        self.status_for("backend")
    }

    fn start_frontend(&self) -> ServiceStatus {
        if self.frontend_mode == "static" {
            return ServiceStatus {
                name: "frontend".to_string(),
                running: true,
                healthy: true,
                log_path: self.service_log("frontend"),
                detail: "static mode (served by backend)".to_string(),
            };
        }

        let mut status = self.status_for("frontend");
        if status.running && status.healthy {
            status.detail = format!("already running on http://{}:{}", self.vite_host, self.vite_port);
            return status;
        }

        let react_dir = self.repo_root.join("react");
        let cmd = vec![
            "npm".to_string(),
            "run".to_string(),
            "dev".to_string(),
            "--".to_string(),
            "--port".to_string(),
            self.vite_port.to_string(),
            "--host".to_string(),
        ];

        let api_url = format!("http://{}:{}", self.backend_host, self.backend_port);
        let ws_url = format!("ws://{}:{}", self.backend_host, self.backend_port);
        let envs = vec![
            ("VITE_API_URL", api_url.as_str()),
            ("VITE_WS_URL", ws_url.as_str()),
        ];
        let proc_pid = self.spawn_service("frontend", &cmd, &react_dir, envs);
        if !self.wait_for_port(&self.vite_host, self.vite_port, 30.0, 0.3) {
            self.terminate_pid(proc_pid);
            panic!("Frontend failed to start on port {}", self.vite_port);
        }

        self.status_for("frontend")
    }

    fn stop_service(&self, name: &str) -> ServiceStatus {
        if let Some(pid) = self.read_pid(name) {
            self.terminate_pid(pid);
            let _ = fs::remove_file(self.pid_file(name));
        }
        let mut status = self.status_for(name);
        status.detail = "stopped".to_string();
        status
    }

    fn status_for(&self, name: &str) -> ServiceStatus {
        let pid = self.read_pid(name);
        let running = pid.map(|p| self.pid_alive(p)).unwrap_or(false);

        let healthy = if running {
            if name == "backend" {
                self.wait_for_port(&self.backend_host, self.backend_port, 0.5, 0.1)
            } else {
                self.wait_for_port(&self.vite_host, self.vite_port, 0.5, 0.1)
            }
        } else {
            false
        };

        let detail = if pid.is_none() {
            "not started"
        } else if !running {
            "stale pid"
        } else if !healthy {
            "running but unhealthy"
        } else {
            ""
        };

        ServiceStatus {
            name: name.to_string(),
            running,
            healthy,
            log_path: self.service_log(name),
            detail: detail.to_string(),
        }
    }

    fn expand_target(&self, target: &str) -> Vec<String> {
        if target == "all" {
            vec!["backend".to_string(), "frontend".to_string()]
        } else {
            vec![target.to_string()]
        }
    }

    fn spawn_service(
        &self,
        name: &str,
        cmd: &[String],
        cwd: &Path,
        env_overrides: Vec<(&str, &str)>,
    ) -> u32 {
        let log_file = File::create(self.service_log(name)).expect("Failed to create log file");

        let mut command = if cfg!(windows) {
            let mut c = Command::new("cmd");
            c.arg("/C");
            c.arg(cmd.join(" "));
            c
        } else {
            let mut c = Command::new("sh");
            c.arg("-c");
            c.arg(format!("exec {}", cmd.join(" ")));
            c
        };

        command.current_dir(cwd);
        command.stdout(Stdio::from(log_file.try_clone().unwrap()));
        command.stderr(Stdio::from(log_file));

        for (k, v) in env_overrides {
            command.env(k, v);
        }

        let child = command.spawn().expect("Failed to spawn process");
        let pid = child.id();
        self.write_pid(name, pid, cmd, cwd);
        pid
    }

    fn terminate_pid(&self, pid: u32) {
        if !self.pid_alive(pid) {
            return;
        }
        if cfg!(windows) {
            let _ = Command::new("taskkill")
                .arg("/F")
                .arg("/PID")
                .arg(pid.to_string())
                .status();
        } else {
            let _ = Command::new("kill").arg("-15").arg(pid.to_string()).status();
            thread::sleep(Duration::from_millis(500));
            if self.pid_alive(pid) {
                let _ = Command::new("kill").arg("-9").arg(pid.to_string()).status();
            }
        }
    }

    fn pid_alive(&self, pid: u32) -> bool {
        if cfg!(windows) {
            if let Ok(output) = Command::new("tasklist")
                .args(&["/FI", &format!("PID eq {}", pid)])
                .output()
            {
                let stdout = String::from_utf8_lossy(&output.stdout);
                stdout.contains(&pid.to_string())
            } else {
                false
            }
        } else {
            if let Ok(status) = Command::new("kill").arg("-0").arg(pid.to_string()).status() {
                status.success()
            } else {
                false
            }
        }
    }

    fn read_pid(&self, name: &str) -> Option<u32> {
        if let Ok(content) = fs::read_to_string(self.pid_file(name)) {
            if let Ok(data) = serde_json::from_str::<PidData>(&content) {
                return Some(data.pid);
            }
        }
        None
    }

    fn write_pid(&self, name: &str, pid: u32, cmd: &[String], cwd: &Path) {
        let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs_f64();
        let data = PidData {
            pid,
            command: cmd.to_vec(),
            cwd: cwd.to_string_lossy().to_string(),
            started_at: now,
        };
        let content = serde_json::to_string(&data).unwrap();
        fs::write(self.pid_file(name), content).ok();
    }

    fn wait_for_port(&self, host: &str, port: u16, timeout: f64, interval: f64) -> bool {
        use std::net::TcpStream;
        let deadline = SystemTime::now() + Duration::from_secs_f64(timeout);
        while SystemTime::now() < deadline {
            if TcpStream::connect_timeout(
                &format!("{}:{}", host, port).parse().unwrap(),
                Duration::from_millis(100),
            )
            .is_ok()
            {
                return true;
            }
            thread::sleep(Duration::from_secs_f64(interval));
        }
        false
    }

    fn service_log(&self, name: &str) -> PathBuf {
        self.service_dir.join(format!("{}.log", name))
    }

    fn pid_file(&self, name: &str) -> PathBuf {
        self.service_dir.join(format!("{}.pid", name))
    }
}
