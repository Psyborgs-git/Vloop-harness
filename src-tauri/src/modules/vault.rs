use std::collections::HashMap;
use std::sync::Mutex;
use serde::{Deserialize, Serialize};
use once_cell::sync::Lazy;

#[derive(Serialize, Deserialize, Clone)]
pub struct VaultCredentials {
    pub keys: HashMap<String, String>,
}

static VAULT: Lazy<Mutex<VaultCredentials>> = Lazy::new(|| {
    Mutex::new(VaultCredentials {
        keys: HashMap::new(),
    })
});

pub fn get_key(name: &str) -> Option<String> {
    let vault = VAULT.lock().unwrap();
    vault.keys.get(name).cloned()
}

pub fn set_key(name: &str, value: &str) {
    let mut vault = VAULT.lock().unwrap();
    vault.keys.insert(name.to_string(), value.to_string());
}

#[tauri::command]
pub fn get_vault_key(name: String) -> Result<String, String> {
    get_key(&name).ok_or_else(|| "Key not found".to_string())
}
