use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs::{self, File};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::{Arc, RwLock};
use std::thread;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct ProcessConfig {
    pub name: String,
    pub command: Vec<String>,
    pub cwd: Option<String>,
    pub env: HashMap<String, String>,
    pub check_port: Option<u16>,
    pub check_host: Option<String>,
}

#[derive(Serialize, Deserialize, Debug)]
struct PidData {
    pid: u32,
    command: Vec<String>,
    cwd: String,
    started_at: f64,
}

#[derive(Debug, Serialize, Clone)]
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
    vite_port: u16,
    frontend_mode: String,
    rust_completions_url: String,
    processes: Arc<RwLock<HashMap<String, ProcessConfig>>>,
}

impl ServiceManager {
    pub fn new(
        repo_root: PathBuf,
        data_dir: PathBuf,
        backend_host: String,
        backend_port: u16,
        vite_port: u16,
        frontend_mode: String,
        rust_completions_url: String,
    ) -> Self {
        let log_dir = data_dir.join("logs");
        let service_dir = log_dir.join("services");
        fs::create_dir_all(&service_dir).ok();

        let mut manager = Self {
            repo_root: repo_root.clone(),
            log_dir,
            service_dir,
            backend_host: backend_host.clone(),
            backend_port,
            vite_port,
            frontend_mode: frontend_mode.clone(),
            rust_completions_url: rust_completions_url.clone(),
            processes: Arc::new(RwLock::new(HashMap::new())),
        };

        manager.register_default_processes();
        manager
    }
pub fn register_process(&self, config: ProcessConfig) {
    let mut processes = self.processes.write().unwrap();
    processes.insert(config.name.clone(), config);
}

fn register_default_processes(&mut self) {
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
                "run".to_string(),
                "--host".to_string(),
                self.backend_host.clone(),
                "--port".to_string(),
                self.backend_port.to_string(),
                "--frontend-mode".to_string(),
                self.frontend_mode.clone(),
            ]
        } else {
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
                    "run".to_string(),
                    "--host".to_string(),
                    self.backend_host.clone(),
                    "--port".to_string(),
                    self.backend_port.to_string(),
                    "--frontend-mode".to_string(),
                    self.frontend_mode.clone(),
                ]
            } else {
                let python_cmd = if cfg!(windows) { "python" } else { "python3" };
                vec![
                    python_cmd.to_string(),
                    "-m".to_string(),
                    "harness.main".to_string(),
                    "run".to_string(),
                    "--host".to_string(),
                    self.backend_host.clone(),
                    "--port".to_string(),
                    self.backend_port.to_string(),
                    "--frontend-mode".to_string(),
                    self.frontend_mode.clone(),
                ]
            }
        };

        let state_db_path = self.log_dir.parent().unwrap().join("state.db").to_string_lossy().to_string();
        let log_dir_str = self.log_dir.to_string_lossy().to_string();
        let cache_dir_str = self.log_dir.parent().unwrap().join("dspy_cache").to_string_lossy().to_string();
        let vite_port_str = self.vite_port.to_string();
        
        let mut envs = HashMap::new();
        envs.insert("RUST_BASE_AI_URL".to_string(), self.rust_completions_url.clone());
        envs.insert("STATE_DB_PATH".to_string(), state_db_path);
        envs.insert("LOG_DIR".to_string(), log_dir_str);
        envs.insert("CACHE_DIR".to_string(), cache_dir_str);
        envs.insert("VITE_PORT".to_string(), vite_port_str);

        let python_orchestrator = ProcessConfig {
            name: "python_orchestrator".to_string(),
            command: cmd,
            cwd: Some(self.repo_root.to_string_lossy().to_string()),
            env: envs,
            check_port: Some(self.backend_port),
            check_host: Some(self.backend_host.clone()),
        };

        self.register_process(python_orchestrator);
    }

    pub fn start(&self, target: &str) -> Vec<ServiceStatus> {
        let targets = self.expand_target(target);
        let mut statuses = Vec::new();
        
        for name in targets {
            let config_opt = {
                let processes = self.processes.read().unwrap();
                processes.get(&name).cloned()
            };

            if let Some(config) = config_opt {
                statuses.push(self.start_process(config));
            } else {
                 statuses.push(ServiceStatus {
                    name: name.clone(),
                    running: false,
                    healthy: false,
                    log_path: self.service_log(&name),
                    detail: format!("Process config not found for {}", name),
                });
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
        let processes = self.processes.read().unwrap();
        for name in processes.keys() {
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
        let status = self.status_for("python_orchestrator");
        status.running && status.healthy
    }

    fn start_process(&self, config: ProcessConfig) -> ServiceStatus {
        let mut status = self.status_for(&config.name);
        if status.running && status.healthy {
            status.detail = "already running".to_string();
            if let (Some(host), Some(port)) = (&config.check_host, config.check_port) {
                status.detail = format!("already running on http://{}:{}", host, port);
            }
            return status;
        }

        let cwd = config.cwd.map(PathBuf::from).unwrap_or_else(|| self.repo_root.clone());
        let env_vec: Vec<(&str, &str)> = config.env.iter().map(|(k, v)| (k.as_str(), v.as_str())).collect();
        
        let proc_pid = self.spawn_service(&config.name, &config.command, &cwd, env_vec);
        
        if let (Some(host), Some(port)) = (&config.check_host, config.check_port) {
            if !self.wait_for_port(host, port, 120.0, 0.3) {
                self.terminate_pid(proc_pid);
                panic!("Process {} failed to start on port {}", config.name, port);
            }
        } else {
            // Give it a brief moment if no port check is configured
            thread::sleep(Duration::from_millis(500));
        }

        self.status_for(&config.name)
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

        let config_opt = {
            let processes = self.processes.read().unwrap();
            processes.get(name).cloned()
        };

        let healthy = if running {
            if let Some(config) = config_opt {
                if let (Some(host), Some(port)) = (config.check_host, config.check_port) {
                    self.wait_for_port(&host, port, 0.5, 0.1)
                } else {
                    true // No health check configured, assume healthy if running
                }
            } else {
                false // Process not registered anymore
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
            let processes = self.processes.read().unwrap();
            processes.keys().cloned().collect()
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

        #[allow(clippy::zombie_processes)]
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
                .args(["/FI", &format!("PID eq {}", pid)])
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

