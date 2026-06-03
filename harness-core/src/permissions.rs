use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, PartialOrd, Ord)]
pub enum Permission {
    #[serde(rename = "filesystem.read")]
    FilesystemRead,
    #[serde(rename = "filesystem.write")]
    FilesystemWrite,
    #[serde(rename = "network.outbound")]
    NetworkOutbound,
    #[serde(rename = "network.inbound")]
    NetworkInbound,
    #[serde(rename = "shell.exec")]
    ShellExec,
    #[serde(rename = "ipc.broadcast")]
    IpcBroadcast,
    #[serde(rename = "ipc.receive")]
    IpcReceive,
    #[serde(rename = "state.persist")]
    StatePersist,
    #[serde(rename = "ui.resize")]
    UiResize,
    #[serde(rename = "ui.spawn")]
    UiSpawn,
    #[serde(rename = "ai.inference")]
    AiInference,
}

impl Permission {
    pub fn as_str(&self) -> &'static str {
        match self {
            Permission::FilesystemRead => "filesystem.read",
            Permission::FilesystemWrite => "filesystem.write",
            Permission::NetworkOutbound => "network.outbound",
            Permission::NetworkInbound => "network.inbound",
            Permission::ShellExec => "shell.exec",
            Permission::IpcBroadcast => "ipc.broadcast",
            Permission::IpcReceive => "ipc.receive",
            Permission::StatePersist => "state.persist",
            Permission::UiResize => "ui.resize",
            Permission::UiSpawn => "ui.spawn",
            Permission::AiInference => "ai.inference",
        }
    }

    pub fn from_str(s: &str) -> Option<Self> {
        match s {
            "filesystem.read" => Some(Permission::FilesystemRead),
            "filesystem.write" => Some(Permission::FilesystemWrite),
            "network.outbound" => Some(Permission::NetworkOutbound),
            "network.inbound" => Some(Permission::NetworkInbound),
            "shell.exec" => Some(Permission::ShellExec),
            "ipc.broadcast" => Some(Permission::IpcBroadcast),
            "ipc.receive" => Some(Permission::IpcReceive),
            "state.persist" => Some(Permission::StatePersist),
            "ui.resize" => Some(Permission::UiResize),
            "ui.spawn" => Some(Permission::UiSpawn),
            "ai.inference" => Some(Permission::AiInference),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct PermissionSet {
    pub granted: HashSet<Permission>,
}

impl PermissionSet {
    pub fn has(&self, permission: &Permission) -> bool {
        self.granted.contains(permission)
    }

    pub fn grant(&mut self, permission: Permission) {
        self.granted.insert(permission);
    }

    pub fn revoke(&mut self, permission: &Permission) {
        self.granted.remove(permission);
    }
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct PermissionsGuard {
    pub sets: HashMap<String, PermissionSet>,
}

impl PermissionsGuard {
    pub fn new() -> Self {
        Self {
            sets: HashMap::new(),
        }
    }

    pub fn has(&self, component_id: &str, permission: &Permission) -> bool {
        if component_id == "root" {
            return true;
        }
        self.sets
            .get(component_id)
            .map(|pset| pset.has(permission))
            .unwrap_or(false)
    }

    pub fn grant(&mut self, component_id: String, permission: Permission) {
        self.sets
            .entry(component_id)
            .or_default()
            .grant(permission);
    }

    pub fn revoke(&mut self, component_id: &str, permission: &Permission) {
        if let Some(pset) = self.sets.get_mut(component_id) {
            pset.revoke(permission);
        }
    }
}
