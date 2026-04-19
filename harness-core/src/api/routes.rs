use axum::{
    extract::{Json, State},
    routing::{get, post},
    Router,
};
use serde::{Deserialize, Serialize};
use std::sync::Arc;

use crate::services::db::DbService;

#[derive(Debug, Deserialize)]
pub struct QueryRequest {
    pub sql: String,
    pub params: Vec<serde_json::Value>,
}

#[derive(Debug, Serialize)]
pub struct QueryResponse {
    pub rows: Vec<serde_json::Value>,
}

async fn handle_query(
    State(db): State<Arc<DbService>>,
    Json(req): Json<QueryRequest>,
) -> Json<serde_json::Value> {
    let mut q = sqlx::query(&req.sql);
    for p in &req.params {
        match p {
            serde_json::Value::String(s) => q = q.bind(s),
            serde_json::Value::Number(n) => q = q.bind(n.as_f64()),
            serde_json::Value::Bool(b) => q = q.bind(b),
            _ => q = q.bind(p.to_string()),
        }
    }
    match q.fetch_all(&db.pool).await {
        Ok(_rows) => Json(serde_json::json!({ "rows": [], "status": "ok" })),
        Err(e) => Json(serde_json::json!({ "error": e.to_string() })),
    }
}

async fn handle_fs_read(Json(req): Json<serde_json::Value>) -> Json<serde_json::Value> {
    let path = req.get("path").and_then(|v| v.as_str()).unwrap_or("");
    match std::fs::read_to_string(path) {
        Ok(content) => Json(serde_json::json!({ "content": content })),
        Err(e) => Json(serde_json::json!({ "error": e.to_string() })),
    }
}

async fn handle_fs_write(Json(req): Json<serde_json::Value>) -> Json<serde_json::Value> {
    let path = req.get("path").and_then(|v| v.as_str()).unwrap_or("");
    let content = req.get("content").and_then(|v| v.as_str()).unwrap_or("");
    match std::fs::write(path, content) {
        Ok(_) => Json(serde_json::json!({ "status": "ok" })),
        Err(e) => Json(serde_json::json!({ "error": e.to_string() })),
    }
}

async fn handle_telemetry_export(
    State(db): State<Arc<DbService>>,
) -> axum::response::Response {
    use axum::http::{header, StatusCode};
    match sqlx::query_as::<_, crate::services::db::models::TelemetryEntry>(
        "SELECT * FROM telemetry ORDER BY id",
    )
    .fetch_all(&db.pool)
    .await
    {
        Ok(entries) => {
            let ndjson: String = entries
                .iter()
                .filter_map(|e| serde_json::to_string(e).ok())
                .collect::<Vec<_>>()
                .join("\n");
            axum::response::Response::builder()
                .status(StatusCode::OK)
                .header(header::CONTENT_TYPE, "application/x-ndjson")
                .body(axum::body::Body::from(ndjson))
                .unwrap()
        }
        Err(e) => axum::response::Response::builder()
            .status(StatusCode::INTERNAL_SERVER_ERROR)
            .body(axum::body::Body::from(e.to_string()))
            .unwrap(),
    }
}

pub fn api_router(db: Arc<DbService>) -> Router {
    Router::new()
        .route("/db/query", post(handle_query))
        .route("/fs/read", post(handle_fs_read))
        .route("/fs/write", post(handle_fs_write))
        .route("/telemetry/export", get(handle_telemetry_export))
        .with_state(db)
}
