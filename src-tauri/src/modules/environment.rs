use serde::{Deserialize, Serialize};
use rusqlite::Connection;
use std::path::PathBuf;
use uuid::Uuid;

#[derive(Serialize, Deserialize, Debug, Clone, PartialEq)]
pub enum EnvironmentType {
    Local,
    Docker,
    Ssh,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct EnvironmentConfig {
    pub env_type: EnvironmentType,
    pub image: Option<String>, // For Docker
    pub host: Option<String>,  // For SSH
    pub user: Option<String>,  // For SSH
    pub extra_config: String,  // JSON string
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
    let repo_root = crate::modules::main::get_repo_root();
    let data_dir = crate::modules::main::get_data_dir(&repo_root);
    data_dir.join("processes.db")
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
        .prepare("SELECT id, name, description, env_type, image, host, user, extra_config, created_at, updated_at FROM environments")
        .map_err(|e| e.to_string())?;

    let envs_iter = stmt
        .query_map([], |row| {
            let type_str: String = row.get(3)?;
            let env_type = match type_str.as_str() {
                "Docker" => EnvironmentType::Docker,
                "Ssh" => EnvironmentType::Ssh,
                _ => EnvironmentType::Local,
            };

            Ok(EnvironmentDetail {
                id: row.get(0)?,
                name: row.get(1)?,
                description: row.get(2)?,
                config: EnvironmentConfig {
                    env_type,
                    image: row.get(4)?,
                    host: row.get(5)?,
                    user: row.get(6)?,
                    extra_config: row.get(7)?,
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
        .prepare("SELECT id, name, description, env_type, image, host, user, extra_config, created_at, updated_at FROM environments WHERE id = ?1")
        .map_err(|e| e.to_string())?;

    let env = stmt
        .query_row([&id], |row| {
            let type_str: String = row.get(3)?;
            let env_type = match type_str.as_str() {
                "Docker" => EnvironmentType::Docker,
                "Ssh" => EnvironmentType::Ssh,
                _ => EnvironmentType::Local,
            };

            Ok(EnvironmentDetail {
                id: row.get(0)?,
                name: row.get(1)?,
                description: row.get(2)?,
                config: EnvironmentConfig {
                    env_type,
                    image: row.get(4)?,
                    host: row.get(5)?,
                    user: row.get(6)?,
                    extra_config: row.get(7)?,
                },
                created_at: row.get(8)?,
                updated_at: row.get(9)?,
            })
        })
        .map_err(|e| e.to_string())?;

    Ok(env)
}

#[tauri::command]
pub fn create_environment(name: String, description: String, config: EnvironmentConfig) -> Result<EnvironmentDetail, String> {
    let conn = get_conn()?;
    let id = Uuid::new_v4().to_string();
    let now = chrono::Utc::now().to_rfc3339();
    
    let env_type_str = match config.env_type {
        EnvironmentType::Local => "Local",
        EnvironmentType::Docker => "Docker",
        EnvironmentType::Ssh => "Ssh",
    };

    conn.execute(
        "INSERT INTO environments (id, name, description, env_type, image, host, user, extra_config, created_at, updated_at) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10)",
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
        ],
    )
    .map_err(|e| e.to_string())?;

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
    };

    conn.execute(
        "UPDATE environments SET name = ?1, description = ?2, env_type = ?3, image = ?4, host = ?5, user = ?6, extra_config = ?7, updated_at = ?8 WHERE id = ?9",
        rusqlite::params![
            name,
            description,
            env_type_str,
            config.image,
            config.host,
            config.user,
            config.extra_config,
            now,
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
    Ok(())
}
