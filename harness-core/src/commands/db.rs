use anyhow::Result;
use tauri::State;

use crate::AppState;

#[tauri::command]
pub async fn db_query(
    sql: String,
    params: Vec<serde_json::Value>,
    state: State<'_, AppState>,
) -> Result<Vec<serde_json::Value>, String> {
    // Use raw execute for simplicity; in a real implementation parse result columns
    let pool = &state.db.pool;

    // Build and run query with bound params
    let mut q = sqlx::query(&sql);
    for p in &params {
        match p {
            serde_json::Value::String(s) => q = q.bind(s),
            serde_json::Value::Number(n) => q = q.bind(n.as_f64()),
            serde_json::Value::Bool(b) => q = q.bind(b),
            serde_json::Value::Null => q = q.bind(Option::<String>::None),
            _ => q = q.bind(p.to_string()),
        }
    }

    let rows = q.fetch_all(pool).await.map_err(|e| e.to_string())?;

    // Convert using sqlx column API
    use sqlx::Column;
    use sqlx::Row;
    let result: Vec<serde_json::Value> = rows
        .iter()
        .map(|row| {
            let mut map = serde_json::Map::new();
            for col in row.columns() {
                let name = col.name().to_string();
                // Try most common types
                let val: serde_json::Value =
                    if let Ok(v) = row.try_get::<i64, _>(col.ordinal()) {
                        serde_json::Value::Number(v.into())
                    } else if let Ok(v) = row.try_get::<f64, _>(col.ordinal()) {
                        serde_json::Number::from_f64(v)
                            .map(serde_json::Value::Number)
                            .unwrap_or(serde_json::Value::Null)
                    } else if let Ok(v) = row.try_get::<bool, _>(col.ordinal()) {
                        serde_json::Value::Bool(v)
                    } else if let Ok(v) = row.try_get::<String, _>(col.ordinal()) {
                        serde_json::Value::String(v)
                    } else {
                        serde_json::Value::Null
                    };
                map.insert(name, val);
            }
            serde_json::Value::Object(map)
        })
        .collect();
    Ok(result)
}

#[tauri::command]
pub async fn db_get_agent_runs(
    limit: i64,
    offset: i64,
    state: State<'_, AppState>,
) -> Result<Vec<serde_json::Value>, String> {
    let rows = sqlx::query_as::<_, crate::services::db::models::AgentRun>(
        "SELECT * FROM agent_runs ORDER BY created_at DESC LIMIT ? OFFSET ?",
    )
    .bind(limit)
    .bind(offset)
    .fetch_all(&state.db.pool)
    .await
    .map_err(|e| e.to_string())?;
    serde_json::to_value(rows)
        .map(|v| v.as_array().cloned().unwrap_or_default())
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn db_get_logs(
    run_id: String,
    limit: i64,
    state: State<'_, AppState>,
) -> Result<Vec<serde_json::Value>, String> {
    let rows = sqlx::query_as::<_, crate::services::db::models::AgentStep>(
        "SELECT * FROM agent_steps WHERE run_id = ? ORDER BY step_index LIMIT ?",
    )
    .bind(run_id)
    .bind(limit)
    .fetch_all(&state.db.pool)
    .await
    .map_err(|e| e.to_string())?;
    serde_json::to_value(rows)
        .map(|v| v.as_array().cloned().unwrap_or_default())
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn db_list_tables(
    state: State<'_, AppState>,
) -> Result<Vec<String>, String> {
    let rows: Vec<(String,)> = sqlx::query_as(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name",
    )
    .fetch_all(&state.db.pool)
    .await
    .map_err(|e| e.to_string())?;
    Ok(rows.into_iter().map(|(n,)| n).collect())
}

#[tauri::command]
pub async fn db_config_get(
    key: String,
    state: State<'_, AppState>,
) -> Result<Option<String>, String> {
    let row: Option<(String,)> =
        sqlx::query_as("SELECT value_json FROM app_config WHERE key = ?")
            .bind(key)
            .fetch_optional(&state.db.pool)
            .await
            .map_err(|e| e.to_string())?;
    Ok(row.map(|(v,)| v))
}

#[tauri::command]
pub async fn db_config_set(
    key: String,
    value: String,
    state: State<'_, AppState>,
) -> Result<(), String> {
    let ts = chrono::Utc::now().to_rfc3339();
    sqlx::query(
        "INSERT INTO app_config (key, value_json, updated_at) VALUES (?, ?, ?)
         ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json, updated_at = excluded.updated_at",
    )
    .bind(key)
    .bind(value)
    .bind(ts)
    .execute(&state.db.pool)
    .await
    .map_err(|e| e.to_string())?;
    Ok(())
}


#[tauri::command]
pub async fn db_get_agent_runs(
    limit: i64,
    offset: i64,
    state: State<'_, AppState>,
) -> Result<Vec<serde_json::Value>, String> {
    let rows = sqlx::query_as::<_, crate::services::db::models::AgentRun>(
        "SELECT * FROM agent_runs ORDER BY created_at DESC LIMIT ? OFFSET ?",
    )
    .bind(limit)
    .bind(offset)
    .fetch_all(&state.db.pool)
    .await
    .map_err(|e| e.to_string())?;
    serde_json::to_value(rows)
        .map(|v| v.as_array().cloned().unwrap_or_default())
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn db_get_logs(
    run_id: String,
    limit: i64,
    state: State<'_, AppState>,
) -> Result<Vec<serde_json::Value>, String> {
    let rows = sqlx::query_as::<_, crate::services::db::models::AgentStep>(
        "SELECT * FROM agent_steps WHERE run_id = ? ORDER BY step_index LIMIT ?",
    )
    .bind(run_id)
    .bind(limit)
    .fetch_all(&state.db.pool)
    .await
    .map_err(|e| e.to_string())?;
    serde_json::to_value(rows)
        .map(|v| v.as_array().cloned().unwrap_or_default())
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn db_list_tables(
    state: State<'_, AppState>,
) -> Result<Vec<String>, String> {
    let rows: Vec<(String,)> = sqlx::query_as(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name",
    )
    .fetch_all(&state.db.pool)
    .await
    .map_err(|e| e.to_string())?;
    Ok(rows.into_iter().map(|(n,)| n).collect())
}

#[tauri::command]
pub async fn db_config_get(
    key: String,
    state: State<'_, AppState>,
) -> Result<Option<String>, String> {
    let row: Option<(String,)> =
        sqlx::query_as("SELECT value_json FROM app_config WHERE key = ?")
            .bind(key)
            .fetch_optional(&state.db.pool)
            .await
            .map_err(|e| e.to_string())?;
    Ok(row.map(|(v,)| v))
}

#[tauri::command]
pub async fn db_config_set(
    key: String,
    value: String,
    state: State<'_, AppState>,
) -> Result<(), String> {
    let ts = chrono::Utc::now().to_rfc3339();
    sqlx::query(
        "INSERT INTO app_config (key, value_json, updated_at) VALUES (?, ?, ?)
         ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json, updated_at = excluded.updated_at",
    )
    .bind(key)
    .bind(value)
    .bind(ts)
    .execute(&state.db.pool)
    .await
    .map_err(|e| e.to_string())?;
    Ok(())
}
