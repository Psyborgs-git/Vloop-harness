use serde::{Deserialize, Serialize};
use std::path::PathBuf;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VLoopConfig {
    #[serde(rename = "VLOOP_CP_HTTP_PORT")]
    pub cp_http_port: u16,
    #[serde(rename = "VLOOP_CP_AUTOSTART")]
    pub cp_autostart: bool,
    #[serde(rename = "VLOOP_DATABASE_URL")]
    pub database_url: String,
    #[serde(rename = "VLOOP_VECTOR_DB_URL")]
    pub vector_db_url: String,
}

impl Default for VLoopConfig {
    fn default() -> Self {
        Self {
            cp_http_port: 8765,
            cp_autostart: true,
            database_url: "".to_string(),
            vector_db_url: "".to_string(),
        }
    }
}

pub fn get_config_path() -> Option<PathBuf> {
    let home = std::env::var_os("HOME")
        .or_else(|| std::env::var_os("USERPROFILE"))
        .map(PathBuf::from);
    home.map(|h| h.join(".vloop").join("config.json"))
}

pub fn ensure_config_exists() -> Option<VLoopConfig> {
    let config_path = get_config_path()?;
    if !config_path.exists() {
        if let Some(parent) = config_path.parent() {
            let _ = std::fs::create_dir_all(parent);
        }
        let config = VLoopConfig::default();
        if let Ok(content) = serde_json::to_string_pretty(&config) {
            let _ = std::fs::write(&config_path, content);
        }
        Some(config)
    } else {
        match std::fs::read_to_string(&config_path) {
            Ok(content) => serde_json::from_str(&content).ok(),
            Err(_) => None,
        }
    }
}

pub fn load_config_to_env() {
    if let Some(config) = ensure_config_exists() {
        std::env::set_var("VLOOP_CP_HTTP_PORT", config.cp_http_port.to_string());
        std::env::set_var("VLOOP_CP_AUTOSTART", if config.cp_autostart { "true" } else { "false" });
        if !config.database_url.is_empty() {
            std::env::set_var("VLOOP_DATABASE_URL", &config.database_url);
        }
        if !config.vector_db_url.is_empty() {
            std::env::set_var("VLOOP_VECTOR_DB_URL", &config.vector_db_url);
        }
    }
}

pub fn save_config(config: &VLoopConfig) -> std::io::Result<()> {
    if let Some(config_path) = get_config_path() {
        if let Some(parent) = config_path.parent() {
            let _ = std::fs::create_dir_all(parent);
        }
        let content = serde_json::to_string_pretty(config)?;
        std::fs::write(config_path, content)?;
    }
    Ok(())
}
