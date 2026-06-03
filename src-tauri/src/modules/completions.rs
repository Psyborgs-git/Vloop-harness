use axum::{
    extract::State,
    http::StatusCode,
    response::IntoResponse,
    routing::{get, post},
    Json, Router,
};
use reqwest::Client;
use serde::Deserialize;
use serde_json::{json, Value};
use std::sync::{Arc, RwLock};

use super::config::ProviderConfig;
use super::permissions::Permission;
use super::tools;

#[derive(Clone)]
pub struct AppState {
    pub provider: Arc<RwLock<ProviderConfig>>,
    pub client: Client,
    pub tools: Arc<tools::ToolsManager>,
}

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/v1/chat/completions", post(chat_completions))
        .route("/v1/completions", post(legacy_completions))
        .route("/harness/configure_provider", post(configure_provider))
        .route("/harness/tools/execute", post(execute_tool_route))
        .route("/harness/tools/policy", get(get_policy).put(update_policy))
        .route("/harness/tools/confirmations", get(list_confirmations))
        .route("/harness/tools/confirmations/:token", post(confirm_action).delete(cancel_confirmation))
        .route("/harness/permissions/check", post(check_permission))
        .route("/harness/permissions/grant", post(grant_permission))
        .route("/harness/permissions/revoke", post(revoke_permission))
}


async fn configure_provider(
    State(state): State<AppState>,
    Json(payload): Json<ProviderConfig>,
) -> impl IntoResponse {
    let mut config = state.provider.write().unwrap();
    *config = payload;
    (StatusCode::OK, Json(json!({"status": "success"})))
}

#[derive(Deserialize, Debug, Clone)]
struct ChatCompletionRequest {
    #[serde(default)]
    model: Option<String>,
    messages: Vec<Value>,
    #[serde(default)]
    temperature: Option<f64>,
    #[serde(default)]
    max_tokens: Option<u32>,
}

async fn chat_completions(
    State(state): State<AppState>,
    Json(mut req): Json<ChatCompletionRequest>,
) -> impl IntoResponse {
    let config = state.provider.read().unwrap().clone();

    // Always override the model from the provider config so DSPy's hardcoded models don't interfere
    req.model = Some(config.model.clone());

    let response = match config.provider_type.as_str() {
        "anthropic" => call_anthropic(&config, &req, &state.client).await,
        "openai" => call_openai(&config, &req, &state.client).await,
        "ollama" => call_ollama(&config, &req, &state.client).await,
        _ => return (StatusCode::BAD_REQUEST, Json(json!({"error": "Unknown provider"}))),
    };

    match response {
        Ok(v) => (StatusCode::OK, Json(v)),
        Err(e) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"error": e.to_string()})),
        ),
    }
}

async fn call_anthropic(
    config: &ProviderConfig,
    req: &ChatCompletionRequest,
    client: &Client,
) -> Result<Value, String> {
    // Anthropic extracts 'system' message from messages
    let mut system_text = String::new();
    let mut anthropic_messages = Vec::new();

    for msg in &req.messages {
        let role = msg.get("role").and_then(|v| v.as_str()).unwrap_or("");
        let content = msg.get("content").and_then(|v| v.as_str()).unwrap_or("");

        if role == "system" {
            system_text.push_str(content);
            system_text.push('\n');
        } else {
            // map role to user/assistant
            let mapped_role = if role == "assistant" { "assistant" } else { "user" };
            anthropic_messages.push(json!({
                "role": mapped_role,
                "content": content
            }));
        }
    }

    let max_tokens = req.max_tokens.unwrap_or(2048);

    let anthropic_req = json!({
        "model": config.model,
        "system": system_text.trim(),
        "messages": anthropic_messages,
        "max_tokens": max_tokens,
        "temperature": req.temperature.unwrap_or(0.7)
    });

    let res = client
        .post("https://api.anthropic.com/v1/messages")
        .header("x-api-key", &config.api_key)
        .header("anthropic-version", "2023-06-01")
        .json(&anthropic_req)
        .send()
        .await
        .map_err(|e| e.to_string())?;

    if !res.status().is_success() {
        let err = res.text().await.unwrap_or_default();
        return Err(format!("Anthropic API error: {}", err));
    }

    let anthropic_res: Value = res.json().await.map_err(|e| e.to_string())?;

    // Translate back to OpenAI format
    let text = anthropic_res["content"][0]["text"].as_str().unwrap_or("");
    let completion = json!({
        "id": anthropic_res["id"],
        "object": "chat.completion",
        "created": 0,
        "model": config.model,
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": text
            },
            "finish_reason": "stop"
        }]
    });

    Ok(completion)
}

async fn call_openai(
    config: &ProviderConfig,
    req: &ChatCompletionRequest,
    client: &Client,
) -> Result<Value, String> {
    let url = if config.base_url.is_empty() {
        "https://api.openai.com/v1/chat/completions"
    } else {
        &config.base_url
    };

    let openai_req = json!({
        "model": config.model,
        "messages": req.messages,
        "temperature": req.temperature,
        "max_tokens": req.max_tokens
    });

    let res = client
        .post(url)
        .header("Authorization", format!("Bearer {}", config.api_key))
        .json(&openai_req)
        .send()
        .await
        .map_err(|e| e.to_string())?;

    if !res.status().is_success() {
        let err = res.text().await.unwrap_or_default();
        return Err(format!("OpenAI API error: {}", err));
    }

    Ok(res.json().await.map_err(|e| e.to_string())?)
}

async fn call_ollama(
    config: &ProviderConfig,
    req: &ChatCompletionRequest,
    client: &Client,
) -> Result<Value, String> {
    let base = if config.base_url.is_empty() {
        "http://localhost:11434"
    } else {
        &config.base_url
    };

    // We assume the ollama base url includes or we append /v1/chat/completions for openai compatibility
    // Ollama supports native openai compatibility since 0.1.24
    let url = format!("{}/v1/chat/completions", base.trim_end_matches('/'));

    let ollama_req = json!({
        "model": config.model,
        "messages": req.messages,
        "temperature": req.temperature,
        "max_tokens": req.max_tokens
    });

    let res = client
        .post(&url)
        .json(&ollama_req)
        .send()
        .await
        .map_err(|e| e.to_string())?;

    if !res.status().is_success() {
        let err = res.text().await.unwrap_or_default();
        return Err(format!("Ollama API error: {}", err));
    }

    Ok(res.json().await.map_err(|e| e.to_string())?)
}

#[derive(Deserialize, Debug)]
struct LegacyCompletionRequest {
    prompt: String,
    #[serde(default)]
    temperature: Option<f64>,
    #[serde(default)]
    max_tokens: Option<u32>,
}

async fn legacy_completions(
    state: State<AppState>,
    Json(req): Json<LegacyCompletionRequest>,
) -> impl IntoResponse {
    // Transform legacy prompt into chat messages
    let chat_req = ChatCompletionRequest {
        model: None,
        messages: vec![json!({"role": "user", "content": req.prompt})],
        temperature: req.temperature,
        max_tokens: req.max_tokens,
    };

    chat_completions(state, Json(chat_req)).await
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
