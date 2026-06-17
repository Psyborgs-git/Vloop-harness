use serde::{Serialize, Deserialize};
use std::fs;
use std::path::PathBuf;

// Helper to get paths
fn get_file_path(filename: &str) -> Result<PathBuf, String> {
    let vloop_home = crate::fs::get_vloop_home().ok_or_else(|| "Failed to get vloop home".to_string())?;
    Ok(vloop_home.join(filename))
}

fn load_json<T: for<'a> Deserialize<'a>>(filename: &str) -> Result<Vec<T>, String> {
    let path = get_file_path(filename)?;
    if !path.exists() {
        return Ok(Vec::new());
    }
    let data = fs::read_to_string(path).map_err(|e| e.to_string())?;
    let items: Vec<T> = serde_json::from_str(&data).unwrap_or_else(|_| Vec::new());
    Ok(items)
}

fn save_json<T: Serialize>(filename: &str, items: &Vec<T>) -> Result<(), String> {
    let path = get_file_path(filename)?;
    let data = serde_json::to_string_pretty(items).map_err(|e| e.to_string())?;
    fs::write(path, data).map_err(|e| e.to_string())?;
    Ok(())
}

// ---------------- Adapters ----------------

#[derive(Serialize, Deserialize, Clone)]
pub struct Adapter {
    pub id: String,
    pub name: String,
    pub uri: String,
    pub port: String,
    pub user: String,
    pub is_active: bool,
}

#[tauri::command]
pub fn get_adapters() -> Result<Vec<Adapter>, String> {
    load_json("adapters.json")
}

#[tauri::command]
pub fn create_adapter(adapter: Adapter) -> Result<(), String> {
    let mut adapters = get_adapters()?;
    adapters.push(adapter);
    save_json("adapters.json", &adapters)
}

#[tauri::command]
pub fn set_active_adapter(id: String) -> Result<(), String> {
    let mut adapters = get_adapters()?;
    for a in adapters.iter_mut() {
        a.is_active = a.id == id;
    }
    save_json("adapters.json", &adapters)?;
    // Simulate systemd restart delay
    std::thread::sleep(std::time::Duration::from_millis(500));
    Ok(())
}

#[tauri::command]
pub fn delete_adapter(id: String) -> Result<(), String> {
    let mut adapters = get_adapters()?;
    adapters.retain(|a| a.id != id);
    save_json("adapters.json", &adapters)
}

// ---------------- Profiles ----------------

#[derive(Serialize, Deserialize, Clone)]
pub struct Profile {
    pub id: String,
    pub name: String,
    #[serde(rename = "type")]
    pub profile_type: String,
    pub image: String,
    pub llm: String,
    pub budget: u32,
}

#[tauri::command]
pub fn get_profiles() -> Result<Vec<Profile>, String> {
    load_json("profiles.json")
}

#[tauri::command]
pub fn create_profile(profile: Profile) -> Result<(), String> {
    let mut profiles = get_profiles()?;
    profiles.push(profile);
    save_json("profiles.json", &profiles)
}

#[tauri::command]
pub fn delete_profile(id: String) -> Result<(), String> {
    let mut profiles = get_profiles()?;
    profiles.retain(|p| p.id != id);
    save_json("profiles.json", &profiles)
}

// ---------------- Knowledge Base ----------------

#[derive(Serialize, Deserialize, Clone)]
pub struct WatchPath {
    pub id: String,
    pub path: String,
    #[serde(rename = "type")]
    pub path_type: String, // "Local" | "Git"
    pub chunks: u32,
    pub last_indexed: String,
    pub status: String, // "Syncing" | "Synced" | "Error"
}

#[tauri::command]
pub fn get_kb_paths() -> Result<Vec<WatchPath>, String> {
    load_json("kb_paths.json")
}

#[tauri::command]
pub fn add_kb_path(mut path: WatchPath) -> Result<(), String> {
    let mut paths = get_kb_paths()?;
    path.status = "Synced".to_string(); // In a real app, this would start as "Syncing"
    paths.push(path);
    save_json("kb_paths.json", &paths)
}

#[tauri::command]
pub fn delete_kb_path(id: String) -> Result<(), String> {
    let mut paths = get_kb_paths()?;
    paths.retain(|p| p.id != id);
    save_json("kb_paths.json", &paths)
}

// ---------------- Swarm Fleet ----------------

#[derive(Serialize, Deserialize, Clone)]
pub struct SwarmNode {
    pub id: String,
    pub ip: String,
    pub key: String,
    pub cpu: f32,
    pub ram: f32,
    pub status: String,
    pub rules: String,
}

#[tauri::command]
pub fn get_swarm_nodes() -> Result<Vec<SwarmNode>, String> {
    load_json("swarm_nodes.json")
}

#[tauri::command]
pub fn add_swarm_node(node: SwarmNode) -> Result<(), String> {
    let mut nodes = get_swarm_nodes()?;
    nodes.push(node);
    save_json("swarm_nodes.json", &nodes)
}

#[tauri::command]
pub fn update_node_rules(id: String, rules: String) -> Result<(), String> {
    let mut nodes = get_swarm_nodes()?;
    if let Some(node) = nodes.iter_mut().find(|n| n.id == id) {
        node.rules = rules;
    }
    save_json("swarm_nodes.json", &nodes)
}

#[tauri::command]
pub fn delete_swarm_node(id: String) -> Result<(), String> {
    let mut nodes = get_swarm_nodes()?;
    nodes.retain(|n| n.id != id);
    save_json("swarm_nodes.json", &nodes)
}
