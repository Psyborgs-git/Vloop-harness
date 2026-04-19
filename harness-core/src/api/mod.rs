pub mod routes;
pub mod ws_handler;

use anyhow::Result;
use axum::{routing::get, Router};
use std::{net::SocketAddr, sync::Arc};
use tokio::net::TcpListener;
use tower_http::cors::CorsLayer;

use crate::services::db::DbService;

pub async fn start_internal_api(db: Arc<DbService>, port: u16) -> Result<()> {
    let app = Router::new()
        .nest("/api", routes::api_router(db))
        .route("/health", get(|| async { "harness-core OK" }))
        .layer(CorsLayer::permissive());

    let addr = SocketAddr::from(([127, 0, 0, 1], port));
    let listener = TcpListener::bind(addr).await?;
    tracing::info!("Internal REST API on {addr}");
    axum::serve(listener, app).await?;
    Ok(())
}
