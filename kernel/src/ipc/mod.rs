pub mod auth;
pub mod named_pipe;
pub mod uds;

use anyhow::{bail, Result};
use tonic::transport::Channel;

use crate::{
    orchestrator::filesystem::RuntimePaths, proto::kernel_lifecycle_client::KernelLifecycleClient,
};

pub async fn connect_kernel_client(paths: &RuntimePaths) -> Result<KernelLifecycleClient<Channel>> {
    #[cfg(unix)]
    {
        let channel = uds::connect_channel(paths.socket.clone()).await?;
        return Ok(KernelLifecycleClient::new(channel));
    }

    #[cfg(windows)]
    {
        let _ = paths;
        bail!("Windows named-pipe IPC client is not implemented yet");
    }

    #[allow(unreachable_code)]
    {
        let _ = paths;
        bail!("unsupported operating system")
    }
}
