use anyhow::Result;

#[tokio::main]
async fn main() -> Result<()> {
    vloop_kernel::daemon::run_daemon().await
}
