use std::path::Path;
use std::process::Command;
use std::fs;

#[derive(Debug)]
pub struct HealthReport {
    pub python_ok: bool,
    pub node_ok: bool,
    pub db_accessible: bool,
    pub details: String,
}

pub fn check_system_health(repo_root: &Path, data_dir: &Path) -> HealthReport {
    let mut details = String::new();
    let python_ok = Command::new("python3").arg("--version").output().is_ok()
        || Command::new("python").arg("--version").output().is_ok()
        || Command::new(repo_root.join(".venv").join("bin").join("python")).arg("--version").output().is_ok();

    if !python_ok {
        details.push_str("Python not found. ");
    }

    let node_ok = Command::new("node").arg("--version").output().is_ok();
    if !node_ok {
        details.push_str("Node.js not found. ");
    }

    let db_path = data_dir.join("metadata.db");
    // Ensure DB dir exists
    let db_accessible = if let Some(parent) = db_path.parent() {
        if fs::create_dir_all(parent).is_err() {
            details.push_str("Could not create DB directory. ");
            false
        } else {
            true
        }
    } else {
        false
    };

    HealthReport {
        python_ok,
        node_ok,
        db_accessible,
        details,
    }
}

pub fn get_available_port(start_port: u16) -> u16 {
    let mut port = start_port;
    loop {
        if port_scanner::local_port_available(port) {
            return port;
        }
        port += 1;
        if port == 65535 {
            return start_port; // Fallback
        }
    }
}
