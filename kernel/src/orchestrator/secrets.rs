use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum SecretClass {
    ModelCredential,
    InfrastructureCredential,
    ApplicationSecret,
    UserSecret,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum SecretInjectionMode {
    EnvInjection,
    FileMount,
    SessionBinding,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SecretMetadataRecord {
    pub secret_id: String,
    pub class: SecretClass,
    pub created_at_unix_ms: i64,
    pub updated_at_unix_ms: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SecretGrantRecord {
    pub grant_id: String,
    pub secret_id: String,
    pub target_type: String,
    pub target_id: String,
    pub injection_mode: SecretInjectionMode,
    pub expires_at_unix_ms: Option<i64>,
    pub revoked_at_unix_ms: Option<i64>,
}

impl SecretGrantRecord {
    pub fn is_revoked(&self) -> bool {
        self.revoked_at_unix_ms.is_some()
    }
}
