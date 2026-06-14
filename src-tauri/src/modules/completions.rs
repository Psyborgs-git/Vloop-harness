use axum::{
    extract::State,
    http::StatusCode,
    response::IntoResponse,
    routing::{get, post},
    Json, Router,
};
use reqwest::Client;
use serde::Deserialize;
use serde_json::json;
use std::sync::Arc;

use super::permissions::Permission;
use super::tools;

#[derive(Clone)]
pub struct AppState {
    pub client: Client,
    pub tools: Arc<tools::ToolsManager>,
}

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/harness/tools/execute", post(execute_tool_route))
        .route("/harness/tools/policy", get(get_policy).put(update_policy))
        .route("/harness/tools/confirmations", get(list_confirmations))
        .route("/harness/tools/confirmations/:token", post(confirm_action).delete(cancel_confirmation))
        .route("/harness/permissions/check", post(check_permission))
        .route("/harness/permissions/grant", post(grant_permission))
        .route("/harness/permissions/revoke", post(revoke_permission))
}

// ── Tools & Permissions API Handlers ─────────────────────────────────────────

#[derive(Deserialize)]
struct ExecuteRequest {
    tool_name: String,
    component_id: Option<String>,
    session_id: Option<String>,
    params: serde_json::Value,
}

async fn execute_tool_route(
    State(state): State<AppState>,
    Json(payload): Json<ExecuteRequest>,
) -> impl IntoResponse {
    match state.tools.execute(
        &payload.tool_name,
        payload.component_id.as_deref(),
        payload.session_id.as_deref(),
        payload.params,
    ).await {
        Ok(res) => (StatusCode::OK, Json(json!(res))),
        Err(err) => {
            if err.starts_with("ConfirmationRequired: ") {
                let token = err.strip_prefix("ConfirmationRequired: ").unwrap();
                if let Some(pending) = state.tools.confirmations.get(token) {
                    return (StatusCode::ACCEPTED, Json(json!({
                        "requires_confirmation": true,
                        "token": pending.token,
                        "description": pending.description,
                        "risk_level": pending.risk_level,
                        "expires_in_seconds": 60,
                    })));
                }
            }
            (StatusCode::BAD_REQUEST, Json(json!({ "error": err })))
        }
    }
}

async fn get_policy(State(state): State<AppState>) -> impl IntoResponse {
    (StatusCode::OK, Json(state.tools.policy.get_effective()))
}

async fn update_policy(
    State(state): State<AppState>,
    Json(payload): Json<tools::PolicyConfig>,
) -> impl IntoResponse {
    match state.tools.policy.save_project_policy(payload) {
        Ok(_) => (StatusCode::OK, Json(json!(state.tools.policy.get_effective()))),
        Err(e) => (StatusCode::BAD_REQUEST, Json(json!({ "error": e }))),
    }
}

async fn list_confirmations(State(state): State<AppState>) -> impl IntoResponse {
    (StatusCode::OK, Json(state.tools.confirmations.list()))
}

async fn confirm_action(
    State(state): State<AppState>,
    axum::extract::Path(token): axum::extract::Path<String>,
) -> impl IntoResponse {
    match state.tools.confirmations.confirm(&token) {
        Ok(pending) => {
            let mut params = pending.action_params.clone();
            if let Some(obj) = params.as_object_mut() {
                obj.insert("_confirmation_token".to_string(), json!(token));
            }
            let tool_name = match pending.action_name.as_str() {
                "write" | "delete" | "move" => "filesystem",
                "query_write" => "database",
                _ => "terminal",
            };
            match state.tools.execute(tool_name, None, None, params).await {
                Ok(res) => (StatusCode::OK, Json(json!(res))),
                Err(e) => (StatusCode::BAD_REQUEST, Json(json!({ "error": e }))),
            }
        }
        Err(e) => (StatusCode::NOT_FOUND, Json(json!({ "error": e }))),
    }
}

async fn cancel_confirmation(
    State(state): State<AppState>,
    axum::extract::Path(token): axum::extract::Path<String>,
) -> impl IntoResponse {
    state.tools.confirmations.cancel(&token);
    StatusCode::NO_CONTENT
}

#[derive(Deserialize)]
struct PermCheckRequest {
    component_id: String,
    permission: String,
}

async fn check_permission(
    State(state): State<AppState>,
    Json(payload): Json<PermCheckRequest>,
) -> impl IntoResponse {
    if let Some(perm) = Permission::from_str(&payload.permission) {
        let guard = state.tools.permissions.lock().unwrap();
        let has_perm = guard.has(&payload.component_id, &perm);
        (StatusCode::OK, Json(json!({ "has_permission": has_perm })))
    } else {
        (StatusCode::BAD_REQUEST, Json(json!({ "error": "Invalid permission string" })))
    }
}

#[derive(Deserialize)]
struct PermGrantRequest {
    component_id: String,
    permission: String,
}

async fn grant_permission(
    State(state): State<AppState>,
    Json(payload): Json<PermGrantRequest>,
) -> impl IntoResponse {
    if let Some(perm) = Permission::from_str(&payload.permission) {
        let mut guard = state.tools.permissions.lock().unwrap();
        guard.grant(payload.component_id, perm);
        (StatusCode::OK, Json(json!({ "status": "success" })))
    } else {
        (StatusCode::BAD_REQUEST, Json(json!({ "error": "Invalid permission string" })))
    }
}

#[derive(Deserialize)]
struct PermRevokeRequest {
    component_id: String,
    permission: String,
}

async fn revoke_permission(
    State(state): State<AppState>,
    Json(payload): Json<PermRevokeRequest>,
) -> impl IntoResponse {
    if let Some(perm) = Permission::from_str(&payload.permission) {
        let mut guard = state.tools.permissions.lock().unwrap();
        guard.revoke(&payload.component_id, &perm);
        (StatusCode::OK, Json(json!({ "status": "success" })))
    } else {
        (StatusCode::BAD_REQUEST, Json(json!({ "error": "Invalid permission string" })))
    }
}
