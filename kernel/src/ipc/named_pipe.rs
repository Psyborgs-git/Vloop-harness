use anyhow::{bail, Result};
use std::path::PathBuf;

pub async fn connect_channel(_pipe_path: PathBuf) -> Result<()> {
    bail!("Windows named-pipe IPC is not implemented yet")
}
