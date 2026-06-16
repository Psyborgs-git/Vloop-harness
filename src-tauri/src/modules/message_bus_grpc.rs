//! gRPC adapter for the kernel message bus.
//!
//! This is a thin wrapper that delegates all logic to `MessageBus`.
//! It is registered in `lib.rs` alongside the other gRPC services.

use std::pin::Pin;
use std::sync::Arc;

use tonic::{Request, Response, Status};
use tokio_stream::Stream;

use super::message_bus::MessageBus;

pub mod pb {
    tonic::include_proto!("message_bus");
}

use pb::message_bus_service_server::MessageBusService;
use pb::{
    BroadcastRequest, BroadcastResponse,
    ListSubscribersRequest, ListSubscribersResponse,
    Message,
    SendMessageRequest, SendMessageResponse,
    SubscribeRequest,
};

pub struct MyMessageBusService {
    bus: Arc<MessageBus>,
}

impl MyMessageBusService {
    pub fn new(bus: Arc<MessageBus>) -> Self {
        Self { bus }
    }
}

#[tonic::async_trait]
impl MessageBusService for MyMessageBusService {
    // ── SendMessage ───────────────────────────────────────────────────────────

    async fn send_message(
        &self,
        request: Request<SendMessageRequest>,
    ) -> Result<Response<SendMessageResponse>, Status> {
        let req = request.into_inner();

        if req.from_process_id.is_empty() {
            return Err(Status::invalid_argument("from_process_id must not be empty"));
        }
        if req.to_process_id.is_empty() {
            return Err(Status::invalid_argument("to_process_id must not be empty"));
        }

        let message_id = uuid::Uuid::new_v4().to_string();
        let msg = Message {
            id: message_id.clone(),
            from_process_id: req.from_process_id,
            to_process_id: req.to_process_id,
            topic: req.topic,
            payload: req.payload,
            timestamp: chrono::Utc::now().to_rfc3339(),
        };

        let (delivered, queued) = self.bus.send(msg);

        Ok(Response::new(SendMessageResponse {
            delivered,
            queued,
            message_id,
            error: String::new(),
        }))
    }

    // ── Subscribe ─────────────────────────────────────────────────────────────

    type SubscribeStream = Pin<Box<dyn Stream<Item = Result<Message, Status>> + Send + 'static>>;

    async fn subscribe(
        &self,
        request: Request<SubscribeRequest>,
    ) -> Result<Response<Self::SubscribeStream>, Status> {
        let req = request.into_inner();

        if req.process_id.is_empty() {
            return Err(Status::invalid_argument("process_id must not be empty"));
        }

        let process_id = req.process_id.clone();
        let bus = Arc::clone(&self.bus);

        println!(
            "[MessageBus] process '{}' subscribed (topics: {:?})",
            process_id, req.topics
        );

        let stream = self.bus.subscribe(req.process_id.clone(), req.topics);

        // Wrap in a cleanup guard that unsubscribes when the stream is dropped
        // (i.e. when the gRPC connection closes).
        let guarded_stream = GuardedStream {
            inner: Box::pin(stream),
            process_id,
            bus,
        };

        Ok(Response::new(Box::pin(guarded_stream)))
    }

    // ── ListSubscribers ───────────────────────────────────────────────────────

    async fn list_subscribers(
        &self,
        _request: Request<ListSubscribersRequest>,
    ) -> Result<Response<ListSubscribersResponse>, Status> {
        Ok(Response::new(ListSubscribersResponse {
            process_ids: self.bus.list_subscribers(),
        }))
    }

    // ── Broadcast ─────────────────────────────────────────────────────────────

    async fn broadcast(
        &self,
        request: Request<BroadcastRequest>,
    ) -> Result<Response<BroadcastResponse>, Status> {
        let req = request.into_inner();

        if req.from_process_id.is_empty() {
            return Err(Status::invalid_argument("from_process_id must not be empty"));
        }

        let message_id = uuid::Uuid::new_v4().to_string();
        let msg = Message {
            id: message_id.clone(),
            from_process_id: req.from_process_id,
            to_process_id: String::new(), // broadcast — no single recipient
            topic: req.topic,
            payload: req.payload,
            timestamp: chrono::Utc::now().to_rfc3339(),
        };

        let delivered_count = self.bus.broadcast(msg);

        Ok(Response::new(BroadcastResponse {
            delivered_count,
            message_id,
        }))
    }
}

// ── GuardedStream ─────────────────────────────────────────────────────────────
//
// Wraps the inner message stream and automatically calls `bus.unsubscribe()`
// when the stream is dropped (i.e. the client disconnects).

use std::task::{Context, Poll};

struct GuardedStream {
    inner: Pin<Box<dyn Stream<Item = Result<Message, Status>> + Send + 'static>>,
    process_id: String,
    bus: Arc<MessageBus>,
}

impl Stream for GuardedStream {
    type Item = Result<Message, Status>;

    fn poll_next(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<Option<Self::Item>> {
        self.inner.as_mut().poll_next(cx)
    }
}

impl Drop for GuardedStream {
    fn drop(&mut self) {
        println!("[MessageBus] process '{}' unsubscribed", self.process_id);
        self.bus.unsubscribe(&self.process_id);
    }
}
