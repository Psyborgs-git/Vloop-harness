use serde::{Deserialize, Serialize};
use tauri::State;

use crate::AppState;

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct AdapterConfig {
    pub name: String,
    pub adapter_type: String,
    pub url: Option<String>,
    pub path: Option<String>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct AdapterInfo {
    pub id: String,
    pub adapter_type: String,
}

#[tauri::command]
pub async fn gateway_list_adapters(
    state: State<'_, AppState>,
) -> Result<Vec<AdapterInfo>, String> {
    Ok(state.gateway_service.list_adapters())
}

#[tauri::command]
pub async fn gateway_add_adapter(
    config: AdapterConfig,
    state: State<'_, AppState>,
) -> Result<String, String> {
    state
        .gateway_service
        .add_adapter(config)
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn gateway_remove_adapter(
    id: String,
    state: State<'_, AppState>,
) -> Result<(), String> {
    state
        .gateway_service
        .remove_adapter(&id)
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn gateway_send(
    adapter_id: String,
    message: String,
    state: State<'_, AppState>,
) -> Result<(), String> {
    state
        .gateway_service
        .send(&adapter_id, &message)
        .await
        .map_err(|e| e.to_string())
}
