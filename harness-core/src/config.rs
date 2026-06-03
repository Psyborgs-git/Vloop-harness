use serde::{Deserialize, Serialize};
use std::env;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProviderConfig {
    pub provider_type: String,
    pub model: String,
    pub api_key: String,
    pub base_url: String,
}

impl ProviderConfig {
    pub fn from_env() -> Self {
        dotenvy::dotenv().ok();
        
        let provider_type = env::var("DSPY_LM_PROVIDER").unwrap_or_else(|_| "anthropic".to_string());
        let model = env::var("DSPY_LM_MODEL").unwrap_or_else(|_| "claude-3-5-sonnet-20241022".to_string());
        
        let api_key = match provider_type.as_str() {
            "anthropic" => env::var("ANTHROPIC_API_KEY").unwrap_or_default(),
            "openai" => env::var("OPENAI_API_KEY").unwrap_or_default(),
            _ => String::new(),
        };

        let base_url = if provider_type == "ollama" {
            env::var("OLLAMA_BASE_URL").unwrap_or_else(|_| "http://localhost:11434".to_string())
        } else {
            String::new()
        };

        Self {
            provider_type,
            model,
            api_key,
            base_url,
        }
    }
}
