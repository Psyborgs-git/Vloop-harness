use anyhow::Result;
use async_trait::async_trait;

use crate::services::gateway::channel::Channel;

pub struct WebSocketAdapter {
    pub id: String,
    pub url: String,
}

#[async_trait]
impl Channel for WebSocketAdapter {
    fn id(&self) -> &str {
        &self.id
    }

    fn adapter_type(&self) -> &str {
        "websocket"
    }

    async fn connect(&self) -> Result<()> {
        Ok(())
    }

    async fn disconnect(&self) -> Result<()> {
        Ok(())
    }

    async fn send(&self, message: &str) -> Result<()> {
        use tokio_tungstenite::connect_async;
        use tokio_tungstenite::tungstenite::Message;
        use futures_util::SinkExt;

        let (mut ws, _) = connect_async(&self.url).await?;
        ws.send(Message::Text(message.to_string())).await?;
        Ok(())
    }

    async fn health_check(&self) -> bool {
        use tokio_tungstenite::connect_async;
        connect_async(&self.url).await.is_ok()
    }
}
