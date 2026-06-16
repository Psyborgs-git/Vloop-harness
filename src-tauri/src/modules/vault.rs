use std::collections::HashMap;
use std::sync::Mutex;
use serde::{Deserialize, Serialize};
use once_cell::sync::Lazy;
use std::path::PathBuf;

#[derive(Serialize, Deserialize, Clone)]
pub struct VaultCredentials {
    pub keys: HashMap<String, String>,
}

static VAULT: Lazy<Mutex<VaultCredentials>> = Lazy::new(|| {
    Mutex::new(VaultCredentials {
        keys: HashMap::new(),
    })
});

fn get_vault_path() -> PathBuf {
    let repo_root = crate::modules::main::get_repo_root();
    let data_dir = crate::modules::main::get_data_dir(&repo_root);
    data_dir.join("vault.json")
}

pub fn load_vault() {
    let path = get_vault_path();
    if path.exists() {
        if let Ok(content) = std::fs::read_to_string(&path) {
            if let Ok(keys) = serde_json::from_str::<HashMap<String, String>>(&content) {
                if let Ok(mut vault) = VAULT.lock() {
                    vault.keys = keys;
                }
            }
        }
    }
}

pub fn save_vault() -> Result<(), String> {
    let path = get_vault_path();
    let keys = {
        let vault = VAULT.lock().map_err(|e| e.to_string())?;
        vault.keys.clone()
    };
    let content = serde_json::to_string(&keys).map_err(|e| e.to_string())?;
    
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    
    std::fs::write(&path, content).map_err(|e| e.to_string())?;
    
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        if let Ok(metadata) = std::fs::metadata(&path) {
            let mut perms = metadata.permissions();
            perms.set_mode(0o600);
            let _ = std::fs::set_permissions(&path, perms);
        }
    }
    Ok(())
}

pub fn get_key(name: &str) -> Option<String> {
    let vault = VAULT.lock().unwrap();
    vault.keys.get(name).cloned()
}

pub fn get_all_keys() -> HashMap<String, String> {
    let vault = VAULT.lock().unwrap();
    vault.keys.clone()
}

#[allow(dead_code)]
pub fn set_key(name: &str, value: &str) {
    {
        let mut vault = VAULT.lock().unwrap();
        vault.keys.insert(name.to_string(), value.to_string());
    }
    let _ = save_vault();
}

#[allow(dead_code)]
pub fn delete_key(name: &str) {
    {
        let mut vault = VAULT.lock().unwrap();
        vault.keys.remove(name);
    }
    let _ = save_vault();
}

#[tauri::command]
pub fn get_vault_key(name: String) -> Result<String, String> {
    get_key(&name).ok_or_else(|| "Key not found".to_string())
}
