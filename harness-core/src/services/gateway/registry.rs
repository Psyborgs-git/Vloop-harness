use anyhow::{anyhow, Result};
use dashmap::DashMap;
use std::sync::Arc;
use uuid::Uuid;

use crate::commands::gateway::{AdapterConfig, AdapterInfo};
use crate::services::gateway::{
    adapters::{http::HttpAdapter, stdio::StdioAdapter, unix_socket::UnixSocketAdapter, websocket::WebSocketAdapter},
    channel::Channel,
};

pub struct GatewayService {
    adapters: Arc<DashMap<String, Box<dyn Channel>>>,
    app_handle: tauri::AppHandle,
}

impl GatewayService {
    pub fn new(app_handle: tauri::AppHandle) -> Self {
        Self {
            adapters: Arc::new(DashMap::new()),
            app_handle,
        }
    }

    pub fn add_adapter(&self, config: AdapterConfig) -> Result<String> {
        let id = Uuid::new_v4().to_string();
        let adapter: Box<dyn Channel> = match config.adapter_type.as_str() {
            "stdio" => Box::new(StdioAdapter { id: id.clone() }),
            "http" => Box::new(HttpAdapter::new(
                id.clone(),
                config.url.unwrap_or_default(),
            )),
            "websocket" => Box::new(WebSocketAdapter {
                id: id.clone(),
                url: config.url.unwrap_or_default(),
            }),
            "unix_socket" => Box::new(UnixSocketAdapter {
                id: id.clone(),
                path: config.path.unwrap_or_default(),
            }),
            t => return Err(anyhow!("Unknown adapter type: {t}")),
        };
        self.adapters.insert(id.clone(), adapter);
        Ok(id)
    }

    pub fn remove_adapter(&self, id: &str) -> Result<()> {
        self.adapters
            .remove(id)
            .ok_or_else(|| anyhow!("Adapter not found: {id}"))?;
        Ok(())
    }

    pub fn list_adapters(&self) -> Vec<AdapterInfo> {
        self.adapters
            .iter()
            .map(|a| AdapterInfo {
                id: a.id().to_string(),
                adapter_type: a.adapter_type().to_string(),
            })
            .collect()
    }

    pub async fn send(&self, adapter_id: &str, message: &str) -> Result<()> {
        let adapter = self
            .adapters
            .get(adapter_id)
            .ok_or_else(|| anyhow!("Adapter not found: {adapter_id}"))?;
        adapter.send(message).await
    }
}
