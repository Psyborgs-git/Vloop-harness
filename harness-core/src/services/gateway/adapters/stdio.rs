use anyhow::Result;
use async_trait::async_trait;

use crate::services::gateway::channel::Channel;

pub struct StdioAdapter {
    pub id: String,
}

#[async_trait]
impl Channel for StdioAdapter {
    fn id(&self) -> &str {
        &self.id
    }

    fn adapter_type(&self) -> &str {
        "stdio"
    }

    async fn connect(&self) -> Result<()> {
        Ok(())
    }

    async fn disconnect(&self) -> Result<()> {
        Ok(())
    }

    async fn send(&self, message: &str) -> Result<()> {
        println!("{message}");
        Ok(())
    }

    async fn health_check(&self) -> bool {
        true
    }
}
