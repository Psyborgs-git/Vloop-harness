use anyhow::Result;
use axum::{
    extract::{Query, State},
    response::IntoResponse,
    routing::get,
    Json, Router,
};
use std::{collections::HashMap, net::SocketAddr, sync::Arc};
use tokio::net::TcpListener;

use crate::services::db::DbService;
use super::session_token::verify_token;

#[derive(Clone)]
pub struct ServerState {
    pub secret: Arc<Vec<u8>>,
    pub db: Arc<DbService>,
}

/// Check that the token exists in `network_sessions`, is not yet used, and is
/// not revoked.  On success, atomically marks it as used (one-time enforcement).
async fn check_and_consume_token(db: &DbService, token: &str) -> Result<bool> {
    let row: Option<(i64, i64)> = sqlx::query_as(
        "SELECT used, revoked FROM network_sessions WHERE token = ?",
    )
    .bind(token)
    .fetch_optional(&db.pool)
    .await?;

    match row {
        None => Ok(false), // unknown token
        Some((used, revoked)) if used != 0 || revoked != 0 => Ok(false),
        Some(_) => {
            sqlx::query("UPDATE network_sessions SET used = 1 WHERE token = ?")
                .bind(token)
                .execute(&db.pool)
                .await?;
            Ok(true)
        }
    }
}

async fn token_handler(
    State(state): State<ServerState>,
    Query(params): Query<HashMap<String, String>>,
    axum::extract::ConnectInfo(addr): axum::extract::ConnectInfo<SocketAddr>,
) -> impl IntoResponse {
    let ip = addr.ip().to_string();
    if let Some(token) = params.get("vloop_token") {
        // 1. Verify HMAC signature and expiry
        if let Err(e) = verify_token(&state.secret, token) {
            return Json(serde_json::json!({
                "status": "error",
                "error": format!("Token invalid: {e}")
            }));
        }
        // 2. Enforce one-time use via DB
        match check_and_consume_token(&state.db, token).await {
            Ok(true) => Json(serde_json::json!({"status": "ok", "ip": ip})),
            Ok(false) => Json(serde_json::json!({
                "status": "error",
                "error": "token already used or revoked"
            })),
            Err(e) => Json(serde_json::json!({"status": "error", "error": e.to_string()})),
        }
    } else {
        Json(serde_json::json!({"status": "error", "error": "missing vloop_token"}))
    }
}

async fn health_handler() -> &'static str {
    "Vloop Harness LAN Host OK"
}

pub async fn start_lan_server(port: u16, secret: Vec<u8>, db: Arc<DbService>) -> Result<()> {
    let state = ServerState {
        secret: Arc::new(secret),
        db,
    };

    let app = Router::new()
        .route("/", get(token_handler))
        .route("/health", get(health_handler))
        .with_state(state);

    let addr = SocketAddr::from(([0, 0, 0, 0], port));
    let listener = TcpListener::bind(addr).await?;
    tracing::info!("LAN host listening on {addr}");
    axum::serve(
        listener,
        app.into_make_service_with_connect_info::<SocketAddr>(),
    )
    .await?;
    Ok(())
}
