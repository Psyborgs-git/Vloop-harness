use anyhow::Result;
use async_trait::async_trait;

use crate::services::gateway::channel::Channel;

pub struct UnixSocketAdapter {
    pub id: String,
    pub path: String,
}

#[async_trait]
impl Channel for UnixSocketAdapter {
    fn id(&self) -> &str {
        &self.id
    }

    fn adapter_type(&self) -> &str {
        "unix_socket"
    }

    async fn connect(&self) -> Result<()> {
        Ok(())
    }

    async fn disconnect(&self) -> Result<()> {
        Ok(())
    }

    #[cfg(unix)]
    async fn send(&self, message: &str) -> Result<()> {
        use tokio::io::AsyncWriteExt;
        use tokio::net::UnixStream;
        let mut stream = UnixStream::connect(&self.path).await?;
        stream.write_all(message.as_bytes()).await?;
        Ok(())
    }

    #[cfg(not(unix))]
    async fn send(&self, _message: &str) -> Result<()> {
        Err(anyhow::anyhow!("Unix sockets not supported on this platform"))
    }

    async fn health_check(&self) -> bool {
        #[cfg(unix)]
        {
            tokio::net::UnixStream::connect(&self.path).await.is_ok()
        }
        #[cfg(not(unix))]
        {
            false
        }
    }
}
