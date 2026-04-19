use anyhow::Result;
use std::sync::Arc;

use crate::services::db::DbService;

/// Append-only telemetry writer.
/// Never issues UPDATE or DELETE — database triggers enforce this too.
pub struct TelemetryWriter {
    db: Arc<DbService>,
}

impl TelemetryWriter {
    pub fn new(db: Arc<DbService>) -> Self {
        Self { db }
    }

    pub async fn log(&self, event_type: &str, payload: serde_json::Value) -> Result<()> {
        let ts = chrono::Utc::now().to_rfc3339();
        sqlx::query(
            "INSERT INTO telemetry (event_type, payload_json, timestamp) VALUES (?, ?, ?)",
        )
        .bind(event_type)
        .bind(payload.to_string())
        .bind(&ts)
        .execute(&self.db.pool)
        .await?;
        Ok(())
    }
}
