use serde::{Deserialize, Serialize};
use rusqlite::Connection;
use std::path::PathBuf;
use uuid::Uuid;

#[derive(Serialize, Deserialize, Debug, Clone, PartialEq)]
pub enum EnvironmentType {
    Local,
    Docker,
    Ssh,
    Python,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct EnvironmentConfig {
    pub env_type: EnvironmentType,
    pub image: Option<String>,       // For Docker
    pub host: Option<String>,        // For SSH
    pub user: Option<String>,        // For SSH
    pub extra_config: String,        // JSON string
    pub path: Option<String>,        // Optional working directory path
    pub python_path: Option<String>, // For Python local environments
    pub ssh_key: Option<String>,     // Optional SSH private key (write-only / masked)
}

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct EnvironmentDetail {
    pub id: String,
    pub name: String,
    pub description: String,
    pub config: EnvironmentConfig,
    pub created_at: String,
    pub updated_at: String,
}

fn get_db_path() -> PathBuf {
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

fn get_conn() -> Result<Connection, String> {
    Connection::open(get_db_path()).map_err(|e| e.to_string())
}

pub fn init_db() -> Result<(), String> {
    let conn = get_conn()?;
    conn.execute(
        "CREATE TABLE IF NOT EXISTS environments (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            env_type TEXT NOT NULL,
            image TEXT,
            host TEXT,
            user TEXT,
            extra_config TEXT,
            created_at TEXT,
            updated_at TEXT
        )",
        [],
    ).map_err(|e| e.to_string())?;

    // Check if columns exist, add if missing
    let mut stmt = conn.prepare("PRAGMA table_info(environments)").map_err(|e| e.to_string())?;
    let mut has_path = false;
    let mut has_python_path = false;
    let rows = stmt.query_map([], |row| Ok(row.get::<_, String>(1)?)).map_err(|e| e.to_string())?;

    for col_name in rows.flatten() {
        if col_name == "path" {
            has_path = true;
        }
        if col_name == "python_path" {
            has_python_path = true;
        }
    }

    if !has_path {
        if let Err(e) = conn.execute("ALTER TABLE environments ADD COLUMN path TEXT", []) {
            eprintln!("Failed to add path column: {}", e);
        }
    }
    if !has_python_path {
        if let Err(e) = conn.execute("ALTER TABLE environments ADD COLUMN python_path TEXT", []) {
            eprintln!("Failed to add python_path column: {}", e);
        }
    }

    // Check if we need to seed the default local environment
    let mut stmt = conn.prepare("SELECT count(*) FROM environments").map_err(|e| e.to_string())?;
    let count: i64 = stmt.query_row([], |row| row.get(0)).unwrap_or(0);

    if count == 0 {
        let now = chrono::Utc::now().to_rfc3339();
        conn.execute(
            "INSERT INTO environments (id, name, description, env_type, extra_config, created_at, updated_at) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
            rusqlite::params![
                "default-local-env-id",
                "Local Machine",
                "Default local execution environment",
                "Local",
                "{}",
                now,
                now,
            ],
        ).map_err(|e| e.to_string())?;
    }
    
    Ok(())
}

#[tauri::command]
pub fn list_environments() -> Result<Vec<EnvironmentDetail>, String> {
    let conn = get_conn()?;
    let mut stmt = conn
        .prepare("SELECT id, name, description, env_type, image, host, user, extra_config, created_at, updated_at, path, python_path FROM environments")
        .map_err(|e| e.to_string())?;

    let envs_iter = stmt
        .query_map([], |row| {
            let id: String = row.get(0)?;
            let type_str: String = row.get(3)?;
            let env_type = match type_str.as_str() {
                "Docker" => EnvironmentType::Docker,
                "Ssh" => EnvironmentType::Ssh,
                "Python" => EnvironmentType::Python,
                _ => EnvironmentType::Local,
            };

            // Check if SSH key exists in vault for this environment
            let has_key = crate::modules::vault::get_key(&format!("ssh_key_{}", id)).is_some();
            let ssh_key = if has_key { Some("********".to_string()) } else { None };

            Ok(EnvironmentDetail {
                id,
                name: row.get(1)?,
                description: row.get(2)?,
                config: EnvironmentConfig {
                    env_type,
                    image: row.get(4)?,
                    host: row.get(5)?,
                    user: row.get(6)?,
                    extra_config: row.get(7)?,
                    path: row.get(10)?,
                    python_path: row.get(11)?,
                    ssh_key,
                },
                created_at: row.get(8)?,
                updated_at: row.get(9)?,
            })
        })
        .map_err(|e| e.to_string())?;

    let mut envs = Vec::new();
    for e in envs_iter {
        if let Ok(env) = e {
            envs.push(env);
        }
    }

    Ok(envs)
}

#[tauri::command]
pub fn get_environment(id: String) -> Result<EnvironmentDetail, String> {
    let conn = get_conn()?;
    let mut stmt = conn
        .prepare("SELECT id, name, description, env_type, image, host, user, extra_config, created_at, updated_at, path, python_path FROM environments WHERE id = ?1")
        .map_err(|e| e.to_string())?;

    let id_clone = id.clone();
    let env = stmt
        .query_row([&id], |row| {
            let type_str: String = row.get(3)?;
            let env_type = match type_str.as_str() {
                "Docker" => EnvironmentType::Docker,
                "Ssh" => EnvironmentType::Ssh,
                "Python" => EnvironmentType::Python,
                _ => EnvironmentType::Local,
            };

            // Check if SSH key exists in vault for this environment
            let has_key = crate::modules::vault::get_key(&format!("ssh_key_{}", id_clone)).is_some();
            let ssh_key = if has_key { Some("********".to_string()) } else { None };

            Ok(EnvironmentDetail {
                id: id_clone,
                name: row.get(1)?,
                description: row.get(2)?,
                config: EnvironmentConfig {
                    env_type,
                    image: row.get(4)?,
                    host: row.get(5)?,
                    user: row.get(6)?,
                    extra_config: row.get(7)?,
                    path: row.get(10)?,
                    python_path: row.get(11)?,
                    ssh_key,
                },
                created_at: row.get(8)?,
                updated_at: row.get(9)?,
            })
        })
        .map_err(|e| e.to_string())?;

    Ok(env)
}

#[tauri::command]
pub fn create_environment(name: String, description: String, mut config: EnvironmentConfig) -> Result<EnvironmentDetail, String> {
    let conn = get_conn()?;
    let id = Uuid::new_v4().to_string();
    let now = chrono::Utc::now().to_rfc3339();
    
    let env_type_str = match config.env_type {
        EnvironmentType::Local => "Local",
        EnvironmentType::Docker => "Docker",
        EnvironmentType::Ssh => "Ssh",
        EnvironmentType::Python => "Python",
    };

    // If SSH key is provided, save it to the Vault
    if config.env_type == EnvironmentType::Ssh {
        if let Some(ref key) = config.ssh_key {
            if !key.is_empty() && key != "********" {
                crate::modules::vault::set_key(&format!("ssh_key_{}", id), key);
            }
        }
    }

    conn.execute(
        "INSERT INTO environments (id, name, description, env_type, image, host, user, extra_config, created_at, updated_at, path, python_path) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12)",
        rusqlite::params![
            id,
            name,
            description,
            env_type_str,
            config.image,
            config.host,
            config.user,
            config.extra_config,
            now,
            now,
            config.path,
            config.python_path,
        ],
    )
    .map_err(|e| e.to_string())?;

    // Mask the key in returning payload
    if config.ssh_key.is_some() {
        config.ssh_key = Some("********".to_string());
    }

    Ok(EnvironmentDetail {
        id,
        name,
        description,
        config,
        created_at: now.clone(),
        updated_at: now,
    })
}

#[tauri::command]
pub fn update_environment(id: String, name: String, description: String, config: EnvironmentConfig) -> Result<EnvironmentDetail, String> {
    let conn = get_conn()?;
    let now = chrono::Utc::now().to_rfc3339();

    let env_type_str = match config.env_type {
        EnvironmentType::Local => "Local",
        EnvironmentType::Docker => "Docker",
        EnvironmentType::Ssh => "Ssh",
        EnvironmentType::Python => "Python",
    };

    // If SSH key is provided and modified, save it to the Vault
    if config.env_type == EnvironmentType::Ssh {
        if let Some(ref key) = config.ssh_key {
            if !key.is_empty() && key != "********" {
                crate::modules::vault::set_key(&format!("ssh_key_{}", id), key);
            }
        }
    }

    conn.execute(
        "UPDATE environments SET name = ?1, description = ?2, env_type = ?3, image = ?4, host = ?5, user = ?6, extra_config = ?7, updated_at = ?8, path = ?9, python_path = ?10 WHERE id = ?11",
        rusqlite::params![
            name,
            description,
            env_type_str,
            config.image,
            config.host,
            config.user,
            config.extra_config,
            now,
            config.path,
            config.python_path,
            id,
        ],
    )
    .map_err(|e| e.to_string())?;

    get_environment(id)
}

#[tauri::command]
pub fn delete_environment(id: String) -> Result<(), String> {
    if id == "default-local-env-id" {
        return Err("Cannot delete the default local environment".to_string());
    }
    let conn = get_conn()?;
    conn.execute("DELETE FROM environments WHERE id = ?1", [&id]).map_err(|e| e.to_string())?;
    
    // Also remove SSH key from vault
    crate::modules::vault::delete_key(&format!("ssh_key_{}", id));
    Ok(())
}
