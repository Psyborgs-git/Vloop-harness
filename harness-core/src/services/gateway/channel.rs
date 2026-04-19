use anyhow::Result;
use async_trait::async_trait;

#[async_trait]
pub trait Channel: Send + Sync {
    fn id(&self) -> &str;
    fn adapter_type(&self) -> &str;
    async fn connect(&self) -> Result<()>;
    async fn disconnect(&self) -> Result<()>;
    async fn send(&self, message: &str) -> Result<()>;
    async fn health_check(&self) -> bool;
}
