use serde::{Deserialize, Serialize};
use rusqlite::Connection;
use std::path::PathBuf;

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct ProcessConfig {
    pub command: String,
    pub args: Vec<String>,
    pub env_vars: String,
    pub cwd: String,
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

fn get_db_path() -> PathBuf {
    let repo_root = crate::modules::main::get_repo_root();
    let data_dir = crate::modules::main::get_data_dir(&repo_root);
    data_dir.join("processes.db")
}

fn get_conn() -> Result<Connection, String> {
    Connection::open(get_db_path()).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn list_processes() -> Result<Vec<ProcessDetail>, String> {
    let conn = get_conn()?;
    let mut stmt = conn
        .prepare("SELECT id, name, description, command, args, env_vars, cwd, status, created_at, updated_at FROM processes")
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
        .prepare("SELECT id, name, description, command, args, env_vars, cwd, status, created_at, updated_at FROM processes WHERE id = ?1")
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
        "INSERT INTO processes (id, name, description, command, args, env_vars, cwd, status, created_at, updated_at) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10)",
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
        "UPDATE processes SET name = ?1, description = ?2, command = ?3, args = ?4, env_vars = ?5, cwd = ?6, updated_at = ?7 WHERE id = ?8",
        rusqlite::params![
            name,
            description,
            config.command,
            args_json,
            config.env_vars,
            config.cwd,
            now,
            id,
        ],
    )
    .map_err(|e| e.to_string())?;

    get_process(id)
}

#[tauri::command]
pub fn delete_process(id: String) -> Result<(), String> {
    let conn = get_conn()?;
    conn.execute("DELETE FROM processes WHERE id = ?1", [&id]).map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
pub fn start_process(id: String) -> Result<(), String> {
    let conn = get_conn()?;
    conn.execute("UPDATE processes SET status = 'running' WHERE id = ?1", [&id]).map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
pub fn stop_process(id: String) -> Result<(), String> {
    let conn = get_conn()?;
    conn.execute("UPDATE processes SET status = 'stopped' WHERE id = ?1", [&id]).map_err(|e| e.to_string())?;
    Ok(())
}
