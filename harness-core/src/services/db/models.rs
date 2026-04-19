use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, sqlx::FromRow)]
pub struct AgentRun {
    pub id: String,
    pub agent_name: String,
    pub agent_loop: String,
    pub task: String,
    pub status: String,
    pub created_at: String,
    pub finished_at: Option<String>,
    pub config_json: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, sqlx::FromRow)]
pub struct AgentStep {
    pub id: String,
    pub run_id: String,
    pub step_index: i64,
    pub step_type: String,
    pub content: String,
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, sqlx::FromRow)]
pub struct TelemetryEntry {
    pub id: i64,
    pub event_type: String,
    pub payload_json: String,
    pub timestamp: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, sqlx::FromRow)]
pub struct AppConfigRow {
    pub key: String,
    pub value_json: String,
    pub updated_at: String,
}
