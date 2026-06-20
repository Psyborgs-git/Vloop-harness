use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum NetworkExposurePolicy {
    Disabled,
    LoopbackOnly,
    LocalPreview,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PortLeaseRecord {
    pub lease_id: String,
    pub service_name: String,
    pub host: String,
    pub host_port: u16,
    pub target_port: u16,
    pub policy: NetworkExposurePolicy,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PreviewUrl {
    pub service_name: String,
    pub url: String,
    pub host_port: u16,
}

impl PreviewUrl {
    pub fn loopback_http(service_name: impl Into<String>, host_port: u16) -> Self {
        Self {
            service_name: service_name.into(),
            url: format!("http://127.0.0.1:{host_port}"),
            host_port,
        }
    }
}
