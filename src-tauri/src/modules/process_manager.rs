use serde::{Deserialize, Serialize};
use rusqlite::Connection;
use std::path::PathBuf;
use once_cell::sync::Lazy;
use std::sync::Mutex;
use std::collections::HashMap;

pub static ACTIVE_PROCESSES: Lazy<Mutex<HashMap<String, std::process::Child>>> = Lazy::new(|| Mutex::new(HashMap::new()));

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct PortBinding {
    pub name: String,
    pub port: u32,
    pub protocol: String,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct ProcessConfig {
    pub command: String,
    pub args: Vec<String>,
    pub env_vars: String,
    pub cwd: String,
    pub environment_id: Option<String>,
    pub autostart: bool,
    pub process_type: String,
    pub ports: Vec<PortBinding>,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct ProcessDetail {
    pub id: String,
    pub name: String,
    pub description: String,
    pub config: ProcessConfig,
    pub status: String,
    pub created_at: String,
    pub updated_at: String,
}

pub fn get_db_path() -> PathBuf {
    #[cfg(test)]
    {
        let tmp_dir = std::env::temp_dir().join("vloop_tests");
        let _ = std::fs::create_dir_all(&tmp_dir);
        tmp_dir.join("processes_test.db")
    }
    #[cfg(not(test))]
    {
        let repo_root = crate::modules::main::get_repo_root();
        let data_dir = crate::modules::main::get_data_dir(&repo_root);
        data_dir.join("processes.db")
    }
}

pub fn get_conn() -> Result<Connection, String> {
    Connection::open(get_db_path()).map_err(|e| e.to_string())
}

pub fn init_db() -> Result<(), String> {
    let conn = get_conn()?;
    conn.execute(
        "CREATE TABLE IF NOT EXISTS processes (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            command TEXT,
            args TEXT,
            env_vars TEXT,
            cwd TEXT,
            status TEXT,
            created_at TEXT,
            updated_at TEXT,
            environment_id TEXT,
            autostart BOOLEAN DEFAULT 0,
            process_type TEXT DEFAULT 'SERVICE',
            ports TEXT DEFAULT '[]'
        )",
        (),
    ).map_err(|e| e.to_string())?;
    
    // Check if columns exist, add if missing
    let mut stmt = conn.prepare("PRAGMA table_info(processes)").map_err(|e| e.to_string())?;
    let mut has_env_id = false;
    let mut has_autostart = false;
    let mut has_process_type = false;
    let mut has_ports = false;
    let rows = stmt.query_map([], |row| Ok(row.get::<_, String>(1)?)).map_err(|e| e.to_string())?;
    
    for col_name in rows.flatten() {
        if col_name == "environment_id" {
            has_env_id = true;
        }
        if col_name == "autostart" {
            has_autostart = true;
        }
        if col_name == "process_type" {
            has_process_type = true;
        }
        if col_name == "ports" {
            has_ports = true;
        }
    }
    
    if !has_env_id {
        if let Err(e) = conn.execute("ALTER TABLE processes ADD COLUMN environment_id TEXT", []) {
            eprintln!("Failed to add environment_id column: {}", e);
        }
    }
    if !has_autostart {
        if let Err(e) = conn.execute("ALTER TABLE processes ADD COLUMN autostart BOOLEAN DEFAULT 0", []) {
            eprintln!("Failed to add autostart column: {}", e);
        }
    }
    if !has_process_type {
        if let Err(e) = conn.execute("ALTER TABLE processes ADD COLUMN process_type TEXT DEFAULT 'SERVICE'", []) {
            eprintln!("Failed to add process_type column: {}", e);
        }
    }
    if !has_ports {
        if let Err(e) = conn.execute("ALTER TABLE processes ADD COLUMN ports TEXT DEFAULT '[]'", []) {
            eprintln!("Failed to add ports column: {}", e);
        }
    }
    
    Ok(())
}

pub fn ensure_core_services(_data_dir: &PathBuf) -> Result<(), String> {
    init_db()?;
    let conn = get_conn()?;
    let now = chrono::Utc::now().to_rfc3339();

    // Check for Python Backend
    let mut stmt = conn.prepare("SELECT count(*) FROM processes WHERE name = 'Python Backend'").map_err(|e| e.to_string())?;
    let python_count: i64 = stmt.query_row([], |row| row.get(0)).unwrap_or(0);
    
    let repo_root = crate::modules::main::get_repo_root();
    #[cfg(target_os = "windows")]
    let venv_python = repo_root.join(".venv").join("Scripts").join("python.exe");
    #[cfg(not(target_os = "windows"))]
    let venv_python = repo_root.join(".venv").join("bin").join("python");

    let python_args_json = serde_json::to_string(&vec![
        "harness/main.py".to_string(),
        "internal".to_string(),
        "backend-worker".to_string(),
        "--host".to_string(),
        "localhost".to_string(),
        "--port".to_string(),
        "9100".to_string(),
    ]).unwrap_or_else(|_| "[]".to_string());

    if python_count == 0 {
        let id = uuid::Uuid::new_v4().to_string();
        
        conn.execute(
            "INSERT INTO processes (id, name, description, command, args, env_vars, cwd, status, created_at, updated_at, environment_id, autostart, process_type, ports) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14)",
            rusqlite::params![
                id,
                "Python Backend",
                "Core VLoop Engine and APIs",
                venv_python.to_string_lossy().to_string(),
                python_args_json,
                "{}",
                repo_root.to_string_lossy().to_string(),
                "stopped",
                now,
                now,
                "default-local-env-id",
                true,
                "SERVICE",
                "[]",
            ],
        ).map_err(|e| format!("Failed to seed Python Backend core process: {}", e))?;
    } else {
        // Auto-repair "Python Backend" config if it was set to make run-python or other invalid commands
        let mut check_stmt = conn.prepare("SELECT command, args FROM processes WHERE name = 'Python Backend'").map_err(|e| e.to_string())?;
        let needs_repair = if let Ok((cmd, args_str)) = check_stmt.query_row([], |row| Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))) {
            let args: Vec<String> = serde_json::from_str(&args_str).unwrap_or_default();
            cmd == "make" || args.len() < 2 || !args.contains(&"backend-worker".to_string())
        } else {
            false
        };

        if needs_repair {
            println!("Auto-repairing Python Backend command in database...");
            conn.execute(
                "UPDATE processes SET command = ?1, args = ?2, status = 'stopped', autostart = 1 WHERE name = 'Python Backend'",
                rusqlite::params![venv_python.to_string_lossy().to_string(), python_args_json]
            ).map_err(|e| format!("Failed to repair Python Backend config: {}", e))?;
        }
    }

    // Check for Node Frontend
    let mut stmt = conn.prepare("SELECT count(*) FROM processes WHERE name = 'Node Frontend'").map_err(|e| e.to_string())?;
    let node_count: i64 = stmt.query_row([], |row| row.get(0)).unwrap_or(0);
    
    let react_dir = repo_root.join("react");
    let node_args_json = serde_json::to_string(&vec!["run".to_string(), "dev".to_string()]).unwrap_or_else(|_| "[]".to_string());

    if node_count == 0 {
        let id = uuid::Uuid::new_v4().to_string();
        
        conn.execute(
            "INSERT INTO processes (id, name, description, command, args, env_vars, cwd, status, created_at, updated_at, environment_id, autostart, process_type, ports) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14)",
            rusqlite::params![
                id,
                "Node Frontend",
                "Vite React development server",
                "npm",
                node_args_json,
                "{}",
                react_dir.to_string_lossy().to_string(),
                "stopped",
                now,
                now,
                "default-local-env-id",
                false, // Set to false to avoid conflicting with gRPC port 9102 on app startup
                "APP",
                "[]",
            ],
        ).map_err(|e| format!("Failed to seed Node Frontend core process: {}", e))?;
    } else {
        // Auto-repair "Node Frontend" config if it was set to custom workarounds like ls -la
        let mut check_stmt = conn.prepare("SELECT command, args, autostart FROM processes WHERE name = 'Node Frontend'").map_err(|e| e.to_string())?;
        let needs_node_repair = if let Ok((cmd, args_str, autostart)) = check_stmt.query_row([], |row| Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?, row.get::<_, bool>(2)?))) {
            let args: Vec<String> = serde_json::from_str(&args_str).unwrap_or_default();
            cmd == "ls" || args.contains(&"-la".to_string()) || autostart
        } else {
            false
        };

        if needs_node_repair {
            println!("Auto-repairing Node Frontend command in database...");
            conn.execute(
                "UPDATE processes SET command = 'npm', args = ?1, status = 'stopped', autostart = 0 WHERE name = 'Node Frontend'",
                rusqlite::params![node_args_json]
            ).map_err(|e| format!("Failed to repair Node Frontend config: {}", e))?;
        }
    }

    Ok(())
}

pub fn update_backend_port(port: u16) -> Result<(), String> {
    let conn = get_conn()?;
    let mut stmt = conn.prepare("SELECT id, args FROM processes WHERE name = 'Python Backend'").map_err(|e| e.to_string())?;
    let res = stmt.query_row([], |row| Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?)));
    if let Ok((id, args_json)) = res {
        let mut args: Vec<String> = serde_json::from_str(&args_json).unwrap_or_default();
        if let Some(pos) = args.iter().position(|x| x == "--port") {
            if pos + 1 < args.len() {
                args[pos + 1] = port.to_string();
                let new_args_json = serde_json::to_string(&args).unwrap_or_else(|_| "[]".to_string());
                conn.execute(
                    "UPDATE processes SET args = ?1 WHERE id = ?2",
                    rusqlite::params![new_args_json, id],
                ).map_err(|e| e.to_string())?;
            }
        }
    }
    Ok(())
}

pub fn check_and_update_all_statuses() -> Result<(), String> {
    let conn = get_conn()?;
    
    // We only care about processes that the DB currently thinks are "running"
    let mut stmt = conn.prepare("SELECT id, name FROM processes WHERE status = 'running'").map_err(|e| e.to_string())?;
    
    let running_processes: Vec<(String, String)> = stmt.query_map([], |row| {
        Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
    }).map_err(|e| e.to_string())?
    .filter_map(|r| r.ok())
    .collect();
    
    if running_processes.is_empty() {
        return Ok(());
    }

    let mut active_map = ACTIVE_PROCESSES.lock().map_err(|e| e.to_string())?;
    let mut to_remove = Vec::new();
    
    for (id, name) in running_processes {
        let mut should_update_db = false;
        let mut new_status = "stopped".to_string();
        let mut error_msg: Option<String> = None;
        
        if let Some(child) = active_map.get_mut(&id) {
            match child.try_wait() {
                Ok(Some(status)) => {
                    // Process has exited
                    should_update_db = true;
                    to_remove.push(id.clone());
                    if status.success() {
                        new_status = "stopped".to_string();
                    } else {
                        new_status = "error".to_string();
                        error_msg = Some(format!(
                            "Process exited with status: {}", 
                            status.code().map(|c| c.to_string()).unwrap_or_else(|| "signal/unknown".to_string())
                        ));
                    }
                }
                Ok(None) => {
                    // Still running, do nothing
                }
                Err(e) => {
                    // Failed to check status
                    should_update_db = true;
                    to_remove.push(id.clone());
                    new_status = "error".to_string();
                    error_msg = Some(format!("Failed to query process status: {}", e));
                }
            }
        } else {
            // It is marked as running in DB but we don't have it in active map
            should_update_db = true;
            new_status = "stopped".to_string();
        }
        
        if should_update_db {
            conn.execute(
                "UPDATE processes SET status = ?1, updated_at = ?2 WHERE id = ?3",
                rusqlite::params![new_status, chrono::Utc::now().to_rfc3339(), id]
            ).map_err(|e| e.to_string())?;
            
            // If there was an error message, write it to the process log
            if let Some(msg) = error_msg {
                let safe_name = name.replace(|c: char| !c.is_ascii_alphanumeric(), "_");
                let repo_root = crate::modules::main::get_repo_root();
                let data_dir = crate::modules::main::get_data_dir(&repo_root);
                let log_path = data_dir.join("processes").join(&safe_name).join("process.log");
                
                // Append the error to the log file
                if let Ok(mut log_file) = std::fs::OpenOptions::new()
                    .create(true)
                    .append(true)
                    .open(&log_path) 
                {
                    use std::io::Write;
                    let _ = writeln!(log_file, "\n--- SYSTEM ERROR: {} ---", msg);
                }
            }
        }
    }
    
    for id in to_remove {
        active_map.remove(&id);
    }
    
    Ok(())
}

#[tauri::command]
pub fn list_processes() -> Result<Vec<ProcessDetail>, String> {
    let _ = check_and_update_all_statuses();
    let conn = get_conn()?;
    let mut stmt = conn
        .prepare("SELECT id, name, description, command, args, env_vars, cwd, status, created_at, updated_at, environment_id, autostart, process_type, ports FROM processes")
        .map_err(|e| e.to_string())?;

    let processes_iter = stmt
        .query_map([], |row| {
            Ok(ProcessDetail {
                id: row.get(0)?,
                name: row.get(1)?,
                description: row.get(2)?,
                config: ProcessConfig {
                    command: row.get(3)?,
                    args: serde_json::from_str(&row.get::<_, String>(4)?).unwrap_or_default(),
                    env_vars: row.get(5)?,
                    cwd: row.get(6)?,
                    environment_id: row.get(10)?,
                    autostart: row.get::<_, bool>(11).unwrap_or(false),
                    process_type: row.get::<_, String>(12).unwrap_or_else(|_| "SERVICE".to_string()),
                    ports: serde_json::from_str(&row.get::<_, String>(13).unwrap_or_else(|_| "[]".to_string())).unwrap_or_default(),
                },
                status: row.get(7)?,
                created_at: row.get(8)?,
                updated_at: row.get(9)?,
            })
        })
        .map_err(|e| e.to_string())?;

    let mut processes = Vec::new();
    for p in processes_iter {
        if let Ok(process) = p {
            processes.push(process);
        }
    }

    Ok(processes)
}

#[tauri::command]
pub fn get_process(id: String) -> Result<ProcessDetail, String> {
    let _ = check_and_update_all_statuses();
    let conn = get_conn()?;
    let mut stmt = conn
        .prepare("SELECT id, name, description, command, args, env_vars, cwd, status, created_at, updated_at, environment_id, autostart, process_type, ports FROM processes WHERE id = ?1")
        .map_err(|e| e.to_string())?;

    let process = stmt
        .query_row([&id], |row| {
            Ok(ProcessDetail {
                id: row.get(0)?,
                name: row.get(1)?,
                description: row.get(2)?,
                config: ProcessConfig {
                    command: row.get(3)?,
                    args: serde_json::from_str(&row.get::<_, String>(4)?).unwrap_or_default(),
                    env_vars: row.get(5)?,
                    cwd: row.get(6)?,
                    environment_id: row.get(10)?,
                    autostart: row.get::<_, bool>(11).unwrap_or(false),
                    process_type: row.get::<_, String>(12).unwrap_or_else(|_| "SERVICE".to_string()),
                    ports: serde_json::from_str(&row.get::<_, String>(13).unwrap_or_else(|_| "[]".to_string())).unwrap_or_default(),
                },
                status: row.get(7)?,
                created_at: row.get(8)?,
                updated_at: row.get(9)?,
            })
        })
        .map_err(|e| e.to_string())?;

    Ok(process)
}

#[tauri::command]
pub fn create_process(name: String, description: String, config: ProcessConfig) -> Result<ProcessDetail, String> {
    let conn = get_conn()?;
    let id = uuid::Uuid::new_v4().to_string();
    let now = chrono::Utc::now().to_rfc3339();
    let args_json = serde_json::to_string(&config.args).unwrap_or_else(|_| "[]".to_string());
    let ports_json = serde_json::to_string(&config.ports).unwrap_or_else(|_| "[]".to_string());

    conn.execute(
        "INSERT INTO processes (id, name, description, command, args, env_vars, cwd, status, created_at, updated_at, environment_id, autostart, process_type, ports) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14)",
        rusqlite::params![
            id,
            name,
            description,
            config.command,
            args_json,
            config.env_vars,
            config.cwd,
            "stopped",
            now,
            now,
            config.environment_id,
            config.autostart,
            config.process_type,
            ports_json,
        ],
    )
    .map_err(|e| e.to_string())?;

    Ok(ProcessDetail {
        id,
        name,
        description,
        config,
        status: "stopped".to_string(),
        created_at: now.clone(),
        updated_at: now,
    })
}

#[tauri::command]
pub fn update_process(id: String, name: String, description: String, config: ProcessConfig) -> Result<ProcessDetail, String> {
    let conn = get_conn()?;
    let now = chrono::Utc::now().to_rfc3339();
    let args_json = serde_json::to_string(&config.args).unwrap_or_else(|_| "[]".to_string());
    let ports_json = serde_json::to_string(&config.ports).unwrap_or_else(|_| "[]".to_string());

    conn.execute(
        "UPDATE processes SET name = ?1, description = ?2, command = ?3, args = ?4, env_vars = ?5, cwd = ?6, updated_at = ?7, environment_id = ?8, autostart = ?9, process_type = ?10, ports = ?11 WHERE id = ?12",
        rusqlite::params![
            name,
            description,
            config.command,
            args_json,
            config.env_vars,
            config.cwd,
            now,
            config.environment_id,
            config.autostart,
            config.process_type,
            ports_json,
            id,
        ],
    )
    .map_err(|e| e.to_string())?;

    get_process(id)
}

#[tauri::command]
pub fn get_process_ports(id: String) -> Result<Vec<PortBinding>, String> {
    let p = get_process(id)?;
    Ok(p.config.ports)
}

#[tauri::command]
pub fn assign_port(
    id: String,
    port_name: String,
    requested_port: Option<u32>,
    protocol: Option<String>,
) -> Result<PortBinding, String> {
    let mut p = get_process(id.clone())?;
    
    let proto = protocol.unwrap_or_else(|| "tcp".to_string());
    let port = match requested_port {
        Some(port_val) if port_val > 0 => port_val,
        _ => {
            let start = 10000;
            crate::modules::health::get_available_port(start) as u32
        }
    };
    
    let binding = PortBinding {
        name: port_name.clone(),
        port,
        protocol: proto,
    };
    
    if let Some(pos) = p.config.ports.iter().position(|b| b.name == port_name) {
        p.config.ports[pos] = binding.clone();
    } else {
        p.config.ports.push(binding.clone());
    }
    
    update_process(id, p.name, p.description, p.config)?;
    
    Ok(binding)
}

#[tauri::command]
pub fn delete_process(id: String) -> Result<(), String> {
    let _ = stop_process(id.clone()); // Ensure it's dead
    let conn = get_conn()?;
    conn.execute("DELETE FROM processes WHERE id = ?1", [&id]).map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
pub fn start_process(id: String) -> Result<(), String> {
    let conn = get_conn()?;
    let mut stmt = conn
        .prepare("SELECT name, command, args, environment_id, cwd FROM processes WHERE id = ?1")
        .map_err(|e| e.to_string())?;

    let (name, command, args_json, environment_id, cwd): (String, String, String, Option<String>, Option<String>) = stmt
        .query_row([&id], |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?, row.get(4)?)))
        .map_err(|e| e.to_string())?;

    let args: Vec<String> = serde_json::from_str(&args_json).unwrap_or_default();
    
    // Resolve environment
    let env_id_to_use = environment_id.unwrap_or_else(|| "default-local-env-id".to_string());
    
    let env = crate::modules::environment::get_environment(env_id_to_use).map_err(|_| "Failed to load environment configuration. It might be missing.".to_string())?;

    let sandbox_type = match env.config.env_type {
        crate::modules::environment::EnvironmentType::Local => crate::modules::sandbox::SandboxType::Local,
        crate::modules::environment::EnvironmentType::Python => {
            let python_path = env.config.python_path.clone().unwrap_or_default();
            crate::modules::sandbox::SandboxType::Python { python_path }
        },
        crate::modules::environment::EnvironmentType::Docker => {
            let image = env.config.image.unwrap_or_else(|| "ubuntu:latest".to_string());
            crate::modules::sandbox::SandboxType::Docker { image }
        },
        crate::modules::environment::EnvironmentType::Ssh => {
            let host = env.config.host.unwrap_or_else(|| "localhost".to_string());
            let user = env.config.user.unwrap_or_else(|| "root".to_string());
            let ssh_key_vault_name = Some(format!("ssh_key_{}", env.id));
            crate::modules::sandbox::SandboxType::Ssh { host, user, ssh_key_vault_name }
        }
    };

    // Determine the working directory to use (environment path takes precedence if configured)
    let resolved_cwd = if let Some(ref env_path) = env.config.path {
        if !env_path.trim().is_empty() {
            Some(env_path.clone())
        } else {
            cwd.clone()
        }
    } else {
        cwd.clone()
    };

    let req = crate::modules::sandbox::SandboxExecutionRequest {
        sandbox: sandbox_type,
        command,
        args,
        cwd: resolved_cwd,
    };

    println!("Starting process: {} with cwd: {:?}", name, cwd);

    let safe_name = name.replace(|c: char| !c.is_ascii_alphanumeric(), "_");
    let repo_root = crate::modules::main::get_repo_root();
    let data_dir = crate::modules::main::get_data_dir(&repo_root);
    let log_path = data_dir.join("processes").join(&safe_name).join("process.log");

    let child = crate::modules::sandbox::spawn_in_sandbox(req, log_path)?;

    // Store the child
    if let Ok(mut map) = ACTIVE_PROCESSES.lock() {
        map.insert(id.clone(), child);
    }

    conn.execute("UPDATE processes SET status = 'running' WHERE id = ?1", [&id]).map_err(|e| e.to_string())?;

    Ok(())
}

#[tauri::command]
pub fn stop_process(id: String) -> Result<(), String> {
    if let Ok(mut map) = ACTIVE_PROCESSES.lock() {
        if let Some(mut child) = map.remove(&id) {
            #[cfg(unix)]
            {
                let pid = child.id();
                let pgid = -(pid as i32);
                unsafe {
                    let _ = libc::kill(pgid, libc::SIGKILL);
                }
                let _ = child.wait(); // Clean up zombie
            }
            #[cfg(not(unix))]
            {
                let _ = child.kill();
                let _ = child.wait(); // Clean up zombie
            }
        }
    }

    // Update DB even if it wasn't in our active map (it might have crashed)
    let conn = get_conn()?;
    conn.execute(
        "UPDATE processes SET status = 'stopped', updated_at = ?2 WHERE id = ?1",
        rusqlite::params![id, chrono::Utc::now().to_rfc3339()],
    ).map_err(|e| e.to_string())?;
    
    Ok(())
}

/// Stop ALL managed processes — called on kernel shutdown to ensure no orphans.
///
/// This function is intentionally NOT a Tauri command (it takes no args and returns unit).
/// It is called directly from the RunEvent::Exit handler and the ctrlc signal handler.
pub fn stop_all_processes() {
    println!("[ProcessManager] Stopping all managed processes...");

    // 1. Kill everything in the in-memory active map (fast path — these are processes
    //    we spawned in this session and still hold a handle to).
    let drained: Vec<(String, std::process::Child)> = {
        match ACTIVE_PROCESSES.lock() {
            Ok(mut map) => map.drain().collect(),
            Err(e) => {
                eprintln!("[ProcessManager] Failed to lock ACTIVE_PROCESSES: {}", e);
                vec![]
            }
        }
    };

    for (id, mut child) in drained {
        let pid = child.id();
        println!("[ProcessManager] Killing process id={} pid={}", id, pid);

        #[cfg(unix)]
        {
            // Kill the entire process group so child subprocesses (e.g. npm → node) die too
            unsafe {
                let pgid = libc::getpgid(pid as libc::pid_t);
                if pgid > 0 {
                    libc::kill(-pgid, libc::SIGKILL);
                } else {
                    // Fallback: kill just the pid
                    libc::kill(pid as libc::pid_t, libc::SIGKILL);
                }
            }
        }
        #[cfg(not(unix))]
        {
            let _ = child.kill();
        }

        // Reap the zombie — wait() is non-blocking after SIGKILL settles
        match child.wait() {
            Ok(status) => println!("[ProcessManager] pid={} exited with {}", pid, status),
            Err(e) => eprintln!("[ProcessManager] wait() for pid={} failed: {}", pid, e),
        }

        // Mark stopped in DB
        if let Ok(conn) = get_conn() {
            let _ = conn.execute(
                "UPDATE processes SET status = 'stopped', updated_at = ?1 WHERE id = ?2",
                rusqlite::params![chrono::Utc::now().to_rfc3339(), id],
            );
        }
    }

    // 2. Sweep DB: mark any remaining 'running' entries as stopped (covers processes
    //    whose Child handle was lost — e.g. externally started or from a prior run).
    if let Ok(conn) = get_conn() {
        match conn.execute(
            "UPDATE processes SET status = 'stopped', updated_at = ?1 WHERE status = 'running'",
            rusqlite::params![chrono::Utc::now().to_rfc3339()],
        ) {
            Ok(n) if n > 0 => println!("[ProcessManager] Swept {} stale 'running' DB entries to 'stopped'", n),
            Ok(_) => {}
            Err(e) => eprintln!("[ProcessManager] DB sweep failed: {}", e),
        }
    }

    println!("[ProcessManager] All processes stopped.");
}

#[tauri::command]
pub fn read_process_logs(id: String) -> Result<String, String> {
    let process = get_process(id)?;
    let safe_name = process.name.replace(|c: char| !c.is_ascii_alphanumeric(), "_");
    let repo_root = crate::modules::main::get_repo_root();
    let data_dir = crate::modules::main::get_data_dir(&repo_root);
    let log_path = data_dir.join("processes").join(&safe_name).join("process.log");

    if !log_path.exists() {
        return Ok("No logs found for this process.".to_string());
    }

    // Read the last ~100KB of the file
    use std::io::{Read, Seek, SeekFrom};
    let mut file = std::fs::File::open(&log_path).map_err(|e| e.to_string())?;
    let len = file.metadata().map_err(|e| e.to_string())?.len();
    let max_read = 100 * 1024; // 100KB

    if len > max_read {
        file.seek(SeekFrom::End(-(max_read as i64))).map_err(|e| e.to_string())?;
    }

    let mut contents = String::new();
    file.read_to_string(&mut contents).map_err(|e| e.to_string())?;
    Ok(contents)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Duration;

    #[test]
    fn test_process_lifecycle_and_status_sync() {
        let db_path = get_db_path();
        let _ = std::fs::remove_file(&db_path);
        
        init_db().unwrap();
        let _ = crate::modules::environment::init_db();
        
        let config = ProcessConfig {
            command: "echo".to_string(),
            args: vec!["test_harness_output".to_string()],
            env_vars: "{}".to_string(),
            cwd: "/".to_string(),
            environment_id: Some("default-local-env-id".to_string()),
            autostart: false,
        };
        
        let p = create_process("Test Echo".to_string(), "Echo test description".to_string(), config).unwrap();
        assert_eq!(p.status, "stopped");
        
        // Start process
        start_process(p.id.clone()).unwrap();
        
        // Check running status in DB immediately
        let p_running = get_process(p.id.clone()).unwrap();
        assert_eq!(p_running.status, "running");
        
        // Wait for it to complete
        std::thread::sleep(Duration::from_millis(300));
        
        // Dynamic status check
        let p_after = get_process(p.id.clone()).unwrap();
        assert_eq!(p_after.status, "stopped");
    }

    #[test]
    fn test_ensure_core_services_and_repair() {
        let db_path = get_db_path();
        let _ = std::fs::remove_file(&db_path);
        
        init_db().unwrap();
        let _ = crate::modules::environment::init_db();
        
        let conn = get_conn().unwrap();
        conn.execute(
            "INSERT INTO processes (id, name, description, command, args, env_vars, cwd, status, created_at, updated_at, environment_id, autostart) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12)",
            rusqlite::params![
                "id-1",
                "Python Backend",
                "Dirty desc",
                "make",
                "[\"run-python\"]",
                "{}",
                "/",
                "stopped",
                "now",
                "now",
                "default-local-env-id",
                true
            ]
        ).unwrap();
        
        conn.execute(
            "INSERT INTO processes (id, name, description, command, args, env_vars, cwd, status, created_at, updated_at, environment_id, autostart) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12)",
            rusqlite::params![
                "id-2",
                "Node Frontend",
                "Dirty desc 2",
                "ls",
                "[\"-la\"]",
                "{}",
                "/",
                "stopped",
                "now",
                "now",
                "default-local-env-id",
                true
            ]
        ).unwrap();

        let repo_root = crate::modules::main::get_repo_root();
        let data_dir = crate::modules::main::get_data_dir(&repo_root);
        ensure_core_services(&data_dir).unwrap();

        let p_py = get_process("id-1".to_string()).unwrap();
        assert_ne!(p_py.config.command, "make");
        assert!(p_py.config.args.contains(&"backend-worker".to_string()));

        let p_node = get_process("id-2".to_string()).unwrap();
        assert_eq!(p_node.config.command, "npm");
        assert_eq!(p_node.config.autostart, false);
    }
}
