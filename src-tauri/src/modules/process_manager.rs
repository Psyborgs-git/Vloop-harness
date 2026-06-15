use serde::{Deserialize, Serialize};
use rusqlite::Connection;
use std::path::PathBuf;
use once_cell::sync::Lazy;
use std::sync::Mutex;
use std::collections::HashMap;

pub static ACTIVE_PROCESSES: Lazy<Mutex<HashMap<String, std::process::Child>>> = Lazy::new(|| Mutex::new(HashMap::new()));

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct ProcessConfig {
    pub command: String,
    pub args: Vec<String>,
    pub env_vars: String,
    pub cwd: String,
    pub environment_id: Option<String>,
    pub autostart: bool,
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
    let repo_root = crate::modules::main::get_repo_root();
    let data_dir = crate::modules::main::get_data_dir(&repo_root);
    data_dir.join("processes.db")
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
            autostart BOOLEAN DEFAULT 0
        )",
        (),
    ).map_err(|e| e.to_string())?;
    
    // Check if columns exist, add if missing
    let mut stmt = conn.prepare("PRAGMA table_info(processes)").map_err(|e| e.to_string())?;
    let mut has_env_id = false;
    let mut has_autostart = false;
    let rows = stmt.query_map([], |row| Ok(row.get::<_, String>(1)?)).map_err(|e| e.to_string())?;
    
    for col_name in rows.flatten() {
        if col_name == "environment_id" {
            has_env_id = true;
        }
        if col_name == "autostart" {
            has_autostart = true;
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
    
    Ok(())
}

pub fn ensure_core_services(data_dir: &PathBuf) -> Result<(), String> {
    init_db()?;
    let conn = get_conn()?;
    let now = chrono::Utc::now().to_rfc3339();

    // Check for Python Backend
    let mut stmt = conn.prepare("SELECT count(*) FROM processes WHERE name = 'Python Backend'").map_err(|e| e.to_string())?;
    let python_count: i64 = stmt.query_row([], |row| row.get(0)).unwrap_or(0);
    
    if python_count == 0 {
        let id = uuid::Uuid::new_v4().to_string();
        let repo_root = crate::modules::main::get_repo_root();
        
        #[cfg(target_os = "windows")]
        let venv_python = repo_root.join(".venv").join("Scripts").join("python.exe");
        #[cfg(not(target_os = "windows"))]
        let venv_python = repo_root.join(".venv").join("bin").join("python");

        let args_json = serde_json::to_string(&vec!["harness/main.py".to_string()]).unwrap_or_else(|_| "[]".to_string());
        
        let _ = conn.execute(
            "INSERT INTO processes (id, name, description, command, args, env_vars, cwd, status, created_at, updated_at, environment_id, autostart) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12)",
            rusqlite::params![
                id,
                "Python Backend",
                "Core VLoop Engine and APIs",
                venv_python.to_string_lossy().to_string(),
                args_json,
                "{}",
                repo_root.to_string_lossy().to_string(),
                "stopped",
                now,
                now,
                "default-local-env-id",
                true,
            ],
        );
    }

    // Check for Node Frontend
    let mut stmt = conn.prepare("SELECT count(*) FROM processes WHERE name = 'Node Frontend'").map_err(|e| e.to_string())?;
    let node_count: i64 = stmt.query_row([], |row| row.get(0)).unwrap_or(0);
    
    if node_count == 0 {
        let id = uuid::Uuid::new_v4().to_string();
        let repo_root = crate::modules::main::get_repo_root();
        let react_dir = repo_root.join("react");
        let args_json = serde_json::to_string(&vec!["run".to_string(), "dev".to_string()]).unwrap_or_else(|_| "[]".to_string());
        
        let _ = conn.execute(
            "INSERT INTO processes (id, name, description, command, args, env_vars, cwd, status, created_at, updated_at, environment_id, autostart) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12)",
            rusqlite::params![
                id,
                "Node Frontend",
                "Vite React development server",
                "npm",
                args_json,
                "{}",
                react_dir.to_string_lossy().to_string(),
                "stopped",
                now,
                now,
                "default-local-env-id",
                true,
            ],
        );
    }

    Ok(())
}

#[tauri::command]
pub fn list_processes() -> Result<Vec<ProcessDetail>, String> {
    let conn = get_conn()?;
    let mut stmt = conn
        .prepare("SELECT id, name, description, command, args, env_vars, cwd, status, created_at, updated_at, environment_id, autostart FROM processes")
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
    let conn = get_conn()?;
    let mut stmt = conn
        .prepare("SELECT id, name, description, command, args, env_vars, cwd, status, created_at, updated_at, environment_id, autostart FROM processes WHERE id = ?1")
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

    conn.execute(
        "INSERT INTO processes (id, name, description, command, args, env_vars, cwd, status, created_at, updated_at, environment_id, autostart) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12)",
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

    conn.execute(
        "UPDATE processes SET name = ?1, description = ?2, command = ?3, args = ?4, env_vars = ?5, cwd = ?6, updated_at = ?7, environment_id = ?8, autostart = ?9 WHERE id = ?10",
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
            id,
        ],
    )
    .map_err(|e| e.to_string())?;

    get_process(id)
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
        crate::modules::environment::EnvironmentType::Docker => {
            let image = env.config.image.unwrap_or_else(|| "ubuntu:latest".to_string());
            crate::modules::sandbox::SandboxType::Docker { image }
        },
        crate::modules::environment::EnvironmentType::Ssh => {
            let host = env.config.host.unwrap_or_else(|| "localhost".to_string());
            let user = env.config.user.unwrap_or_else(|| "root".to_string());
            crate::modules::sandbox::SandboxType::Ssh { host, user }
        }
    };

    let req = crate::modules::sandbox::SandboxExecutionRequest {
        sandbox: sandbox_type,
        command,
        args,
        cwd: cwd.clone(),
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
    let mut killed = false;
    if let Ok(mut map) = ACTIVE_PROCESSES.lock() {
        if let Some(mut child) = map.remove(&id) {
            let _ = child.kill();
            let _ = child.wait(); // Clean up zombie
            killed = true;
        }
    }

    // Update DB even if it wasn't in our active map (it might have crashed)
    let conn = get_conn()?;
    conn.execute("UPDATE processes SET status = 'stopped' WHERE id = ?1", [&id]).map_err(|e| e.to_string())?;
    
    if killed { Ok(()) } else { Ok(()) /* Return Ok to self-heal state */ }
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
