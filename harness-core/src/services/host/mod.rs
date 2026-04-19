pub mod lan_server;
pub mod qr_service;
pub mod session_token;

use parking_lot::Mutex;
use std::sync::Arc;
use tauri::async_runtime::JoinHandle;

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct HostStatus {
    pub running: bool,
    pub address: Option<String>,
    pub url: Option<String>,
    pub qr_png_base64: Option<String>,
    pub token: Option<String>,
}

pub struct HostService {
    state: Arc<Mutex<HostStatus>>,
    server_handle: Arc<Mutex<Option<JoinHandle<()>>>>,
}

impl HostService {
    pub fn new() -> Self {
        Self {
            state: Arc::new(Mutex::new(HostStatus {
                running: false,
                address: None,
                url: None,
                qr_png_base64: None,
                token: None,
            })),
            server_handle: Arc::new(Mutex::new(None)),
        }
    }

    pub fn get_status(&self) -> HostStatus {
        self.state.lock().clone()
    }

    pub fn update_status(&self, status: HostStatus) {
        *self.state.lock() = status;
    }

    /// Store the background task handle so it can be aborted on `host_stop`.
    pub fn set_server_handle(&self, handle: JoinHandle<()>) {
        *self.server_handle.lock() = Some(handle);
    }

    /// Abort the running LAN server task, if any.
    pub fn abort_server(&self) {
        let mut guard = self.server_handle.lock();
        if let Some(handle) = guard.take() {
            handle.abort();
        }
    }
}
