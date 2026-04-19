use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppConfig {
    pub db_engine: String,
    pub lan_port: u16,
    pub internal_api_port: u16,
    pub inference_backend_port: u16,
    pub theme: String,
    pub lm_provider: String,
    pub lm_model: String,
    pub sandbox_mode: String,
    pub token_ttl_minutes: u64,
}

impl Default for AppConfig {
    fn default() -> Self {
        Self {
            db_engine: "sqlite".into(),
            lan_port: 47299,
            internal_api_port: 47200,
            inference_backend_port: 47201,
            theme: "dark".into(),
            lm_provider: "ollama".into(),
            lm_model: "llama3".into(),
            sandbox_mode: "process".into(),
            token_ttl_minutes: 15,
        }
    }
}
