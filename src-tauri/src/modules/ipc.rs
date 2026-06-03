use serde_json::Value;

pub fn send_to_python(channel: &str, payload: Value) {
    // In production, Rust will use HTTP client to push to python /ipc/rust endpoint
    let rt = tokio::runtime::Runtime::new().unwrap();
    rt.block_on(async {
        let client = reqwest::Client::new();
        // Assume ai_port is 9101 for local, dynamically resolved in production
        let _ = client.post("http://127.0.0.1:9101/api/ipc/rust_push")
            .json(&serde_json::json!({
                "channel": channel,
                "payload": payload
            }))
            .send()
            .await;
    });
}
