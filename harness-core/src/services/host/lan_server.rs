use anyhow::Result;
use axum::{
    extract::{Query, State},
    response::IntoResponse,
    routing::get,
    Json, Router,
};
use std::{collections::HashMap, net::SocketAddr, sync::Arc};
use tokio::net::TcpListener;

use super::session_token::verify_token;

#[derive(Clone)]
pub struct ServerState {
    pub secret: Arc<Vec<u8>>,
}

async fn token_handler(
    State(state): State<ServerState>,
    Query(params): Query<HashMap<String, String>>,
    axum::extract::ConnectInfo(addr): axum::extract::ConnectInfo<SocketAddr>,
) -> impl IntoResponse {
    if let Some(token) = params.get("vloop_token") {
        let ip = addr.ip().to_string();
        match verify_token(&state.secret, token, &ip) {
            Ok(_) => Json(serde_json::json!({"status": "ok", "ip": ip})),
            Err(e) => Json(serde_json::json!({"status": "error", "error": e.to_string()})),
        }
    } else {
        Json(serde_json::json!({"status": "error", "error": "missing vloop_token"}))
    }
}

async fn health_handler() -> &'static str {
    "Vloop Harness LAN Host OK"
}

pub async fn start_lan_server(port: u16, secret: Vec<u8>) -> Result<()> {
    let state = ServerState {
        secret: Arc::new(secret),
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
