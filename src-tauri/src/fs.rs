use std::fs;
use std::path::{Path, PathBuf};
use std::io::Write;
use serde::Serialize;
use toml;

#[derive(Serialize)]
pub struct ActiveConfig {
    pub max_memory_bytes: u64,
    pub data_dir: String,
}

pub fn get_vloop_home() -> Option<PathBuf> {
    dirs::home_dir().map(|mut p| {
        p.push(".vloop");
        p
    })
}

pub fn initialize_filesystem(config: &ActiveConfig) -> Result<(), Box<dyn std::error::Error>> {
    let home = get_vloop_home().ok_or("Could not determine home directory")?;
    
    // Define the directories
    let rust_dir = home.join("rust");
    let control_plane_dir = home.join("control-plane");
    let artifacts_dir = control_plane_dir.join("artifacts");

    // Create directories
    fs::create_dir_all(&rust_dir)?;
    fs::create_dir_all(&artifacts_dir)?;

    // Write active.toml
    let active_toml_path = rust_dir.join("active.toml");
    let toml_string = toml::to_string(config)?;
    let mut file = fs::File::create(active_toml_path)?;
    file.write_all(toml_string.as_bytes())?;

    println!("Initialized VLoop filesystem at {:?}", home);
    Ok(())
}
