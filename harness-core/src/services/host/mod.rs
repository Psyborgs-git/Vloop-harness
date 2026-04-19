pub mod lan_server;
pub mod qr_service;
pub mod session_token;

use std::sync::Arc;
use parking_lot::Mutex;

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
        }
    }

    pub fn get_status(&self) -> HostStatus {
        self.state.lock().clone()
    }

    pub fn update_status(&self, status: HostStatus) {
        *self.state.lock() = status;
    }
}
