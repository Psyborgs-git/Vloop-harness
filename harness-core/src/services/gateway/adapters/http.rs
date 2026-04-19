use anyhow::Result;
use async_trait::async_trait;

use crate::services::gateway::channel::Channel;

pub struct HttpAdapter {
    pub id: String,
    pub url: String,
    client: reqwest::Client,
}

impl HttpAdapter {
    pub fn new(id: String, url: String) -> Self {
        Self {
            id,
            url,
            client: reqwest::Client::new(),
        }
    }
}

#[async_trait]
impl Channel for HttpAdapter {
    fn id(&self) -> &str {
        &self.id
    }

    fn adapter_type(&self) -> &str {
        "http"
    }

    async fn connect(&self) -> Result<()> {
        Ok(())
    }

    async fn disconnect(&self) -> Result<()> {
        Ok(())
    }

    async fn send(&self, message: &str) -> Result<()> {
        self.client
            .post(&self.url)
            .body(message.to_string())
            .send()
            .await?;
        Ok(())
    }

    async fn health_check(&self) -> bool {
        self.client.get(&self.url).send().await.is_ok()
    }
}
