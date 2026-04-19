use tauri::State;

use crate::{
    services::host::{
        qr_service::generate_qr_base64,
        session_token::generate_token,
        HostStatus,
    },
    AppState,
};

const LAN_PORT: u16 = 47299;
const TOKEN_TTL: i64 = 15; // minutes

/// Return the LAN HMAC secret.
/// Priority: VLOOP_LAN_SECRET env var → app_config key 'lan_secret' → auto-generated (persisted).
async fn get_or_create_lan_secret(state: &AppState) -> Result<Vec<u8>, String> {
    // 1. Environment variable override
    if let Ok(s) = std::env::var("VLOOP_LAN_SECRET") {
        return Ok(s.into_bytes());
    }

    // 2. Persisted secret in app_config
    let row: Option<(String,)> = sqlx::query_as(
        "SELECT value_json FROM app_config WHERE key = 'lan_secret'",
    )
    .fetch_optional(&state.db.pool)
    .await
    .map_err(|e| e.to_string())?;

    if let Some((secret_json,)) = row {
        let hex = secret_json.trim_matches('"');
        return hex::decode(hex).map_err(|e| e.to_string());
    }

    // 3. Generate a fresh 32-byte secret, store it for future restarts
    use rand::Rng;
    let secret: [u8; 32] = rand::thread_rng().gen();
    let secret_hex = format!("\"{}\"", hex::encode(secret));
    let ts = chrono::Utc::now().to_rfc3339();
    sqlx::query(
        "INSERT INTO app_config (key, value_json, updated_at) VALUES ('lan_secret', ?, ?) \
         ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json, updated_at = excluded.updated_at",
    )
    .bind(&secret_hex)
    .bind(&ts)
    .execute(&state.db.pool)
    .await
    .map_err(|e| e.to_string())?;

    Ok(secret.to_vec())
}

/// INSERT a new token row into `network_sessions` for one-time-use tracking.
async fn persist_network_session(state: &AppState, token: &str) -> Result<(), String> {
    let now = chrono::Utc::now();
    let expires = now + chrono::Duration::minutes(TOKEN_TTL);
    sqlx::query(
        "INSERT INTO network_sessions (token, created_at, expires_at, used, revoked) \
         VALUES (?, ?, ?, 0, 0)",
    )
    .bind(token)
    .bind(now.to_rfc3339())
    .bind(expires.to_rfc3339())
    .execute(&state.db.pool)
    .await
    .map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
pub async fn host_start(state: State<'_, AppState>) -> Result<HostStatus, String> {
    // Abort any previously running server before spawning a new one
    state.host_service.abort_server();

    let ip = local_ip_address::local_ip()
        .map(|ip| ip.to_string())
        .unwrap_or_else(|_| "127.0.0.1".to_string());

    let secret = get_or_create_lan_secret(&state).await?;
    let token = generate_token(&secret, &ip, TOKEN_TTL).map_err(|e| e.to_string())?;
    persist_network_session(&state, &token).await?;

    let url = format!("http://{}:{}/?vloop_token={}", ip, LAN_PORT, token);
    let qr = generate_qr_base64(&url).map_err(|e| e.to_string())?;

    let db = state.db.clone();
    let handle = tauri::async_runtime::spawn(async move {
        if let Err(e) =
            crate::services::host::lan_server::start_lan_server(LAN_PORT, secret, db).await
        {
            tracing::error!("LAN server error: {e}");
        }
    });

    let status = HostStatus {
        running: true,
        address: Some(format!("{ip}:{LAN_PORT}")),
        url: Some(url),
        qr_png_base64: Some(qr),
        token: Some(token),
    };
    state.host_service.update_status(status.clone());
    state.host_service.set_server_handle(handle);
    Ok(status)
}

#[tauri::command]
pub async fn host_stop(state: State<'_, AppState>) -> Result<(), String> {
    state.host_service.abort_server();
    state.host_service.update_status(HostStatus {
        running: false,
        address: None,
        url: None,
        qr_png_base64: None,
        token: None,
    });
    Ok(())
}

#[tauri::command]
pub async fn host_status(state: State<'_, AppState>) -> Result<HostStatus, String> {
    Ok(state.host_service.get_status())
}

#[tauri::command]
pub async fn host_rotate_token(state: State<'_, AppState>) -> Result<String, String> {
    let ip = local_ip_address::local_ip()
        .map(|ip| ip.to_string())
        .unwrap_or_else(|_| "127.0.0.1".to_string());

    let secret = get_or_create_lan_secret(&state).await?;
    let token = generate_token(&secret, &ip, TOKEN_TTL).map_err(|e| e.to_string())?;
    persist_network_session(&state, &token).await?;

    let url = format!("http://{}:{}/?vloop_token={}", ip, LAN_PORT, token);
    let qr = generate_qr_base64(&url).map_err(|e| e.to_string())?;

    let mut status = state.host_service.get_status();
    status.url = Some(url);
    status.qr_png_base64 = Some(qr);
    status.token = Some(token.clone());
    state.host_service.update_status(status);
    Ok(token)
}
