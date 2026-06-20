use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum DatabaseEngine {
    Sqlite,
    Postgres,
    Redis,
    VectorStore,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum DatabaseLifecycleState {
    Provisioning,
    Ready,
    Degraded,
    Stopped,
    Destroyed,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DatabaseRecord {
    pub database_id: String,
    pub engine: DatabaseEngine,
    pub state: DatabaseLifecycleState,
    pub endpoint_reference: Option<String>,
    pub volume_id: Option<String>,
    pub created_at_unix_ms: i64,
    pub updated_at_unix_ms: i64,
}

impl DatabaseRecord {
    pub fn endpoint_reference(&self) -> Option<&str> {
        self.endpoint_reference.as_deref()
    }
}
