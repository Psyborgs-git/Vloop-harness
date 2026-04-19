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
const TOKEN_TTL: i64 = 15;
const SECRET: &[u8] = b"vloop-harness-secret-change-in-production";

#[tauri::command]
pub async fn host_start(state: State<'_, AppState>) -> Result<HostStatus, String> {
    let ip = local_ip_address::local_ip()
        .map(|ip| ip.to_string())
        .unwrap_or_else(|_| "127.0.0.1".to_string());

    let token = generate_token(SECRET, &ip, TOKEN_TTL).map_err(|e| e.to_string())?;
    let url = format!("http://{}:{}/?vloop_token={}", ip, LAN_PORT, token);
    let qr = generate_qr_base64(&url).map_err(|e| e.to_string())?;

    // Spawn Axum LAN server in background
    let secret = SECRET.to_vec();
    tauri::async_runtime::spawn(async move {
        if let Err(e) =
            crate::services::host::lan_server::start_lan_server(LAN_PORT, secret).await
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
    Ok(status)
}

#[tauri::command]
pub async fn host_stop(state: State<'_, AppState>) -> Result<(), String> {
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
    let token = generate_token(SECRET, &ip, TOKEN_TTL).map_err(|e| e.to_string())?;
    let url = format!("http://{}:{}/?vloop_token={}", ip, LAN_PORT, token);
    let qr = generate_qr_base64(&url).map_err(|e| e.to_string())?;
    let status = HostStatus {
        running: true,
        address: Some(format!("{ip}:{LAN_PORT}")),
        url: Some(url),
        qr_png_base64: Some(qr),
        token: Some(token.clone()),
    };
    state.host_service.update_status(status);
    Ok(token)
}
