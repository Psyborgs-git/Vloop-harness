use anyhow::Result;
use tracing::info;

fn main() -> Result<()> {
    tracing_subscriber::fmt::init();
    info!("vloop-launcher: ensure vloopd running, then open Python-owned UI (stub)");
    // TODO: implement daemon ensure + CP UI open endpoint.
    Ok(())
}
