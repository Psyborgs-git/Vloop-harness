//! In-memory message broker — the kernel routes messages between managed processes.
//!
//! # Architecture
//!
//! ```text
//! Process A                    MessageBus (kernel)               Process B
//!    │                               │                               │
//!    │── send("proc-b", payload) ───▶│                               │
//!    │                         route("proc-b")                       │
//!    │                               ├── tx.send(msg) ──────────────▶│
//!    │◀── SendMessageResponse ───────│                               │
//!    │                               │                               │
//!    │                     Subscribe("proc-b") ◀────────────────────│
//! ```
//!
//! Messages sent to an offline process are stored in an in-memory offline queue
//! (capped at `MAX_OFFLINE_QUEUE` items per process). When that process next calls
//! `Subscribe`, the queue is flushed immediately before new messages arrive.
//! Messages older than `OFFLINE_TTL_SECS` are discarded on flush.

use std::collections::{HashMap, VecDeque};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tokio::sync::mpsc;
use tokio_stream::wrappers::UnboundedReceiverStream;
use tonic::Status;

use crate::modules::message_bus_grpc::pb::Message;

// ── Constants ────────────────────────────────────────────────────────────────

/// Maximum messages held per-process while it has no active subscriber.
const MAX_OFFLINE_QUEUE: usize = 256;

/// Offline messages older than this are discarded when the process reconnects.
const OFFLINE_TTL_SECS: u64 = 60;

// ── Internal queued message (includes arrival time for TTL) ──────────────────

struct QueuedMessage {
    msg: Message,
    arrived_at: Instant,
}

// ── MessageBus ────────────────────────────────────────────────────────────────

/// Shared kernel-level message bus.
///
/// Wrap in `Arc<MessageBus>` and share between the gRPC handler and `lib.rs`.
pub struct MessageBus {
    /// Active subscribers: process_id → channel sender.
    /// Topic filter (empty = all) stored alongside the sender.
    subscribers: Mutex<HashMap<String, SubscriberEntry>>,

    /// Offline queue for processes that are not currently subscribed.
    offline_queue: Mutex<HashMap<String, VecDeque<QueuedMessage>>>,
}

struct SubscriberEntry {
    tx: mpsc::UnboundedSender<Result<Message, Status>>,
    /// Allowed topics — empty vec means receive everything.
    topics: Vec<String>,
}

impl Default for MessageBus {
    fn default() -> Self {
        Self {
            subscribers: Mutex::new(HashMap::new()),
            offline_queue: Mutex::new(HashMap::new()),
        }
    }
}

impl MessageBus {
    pub fn new() -> Self {
        Self::default()
    }

    // ── Subscribe ─────────────────────────────────────────────────────────────

    /// Register a subscriber for `process_id`.
    ///
    /// Returns a stream of `Message` items. Any messages queued while the process
    /// was offline are flushed immediately (after TTL filtering).
    pub fn subscribe(
        &self,
        process_id: String,
        topics: Vec<String>,
    ) -> impl tokio_stream::Stream<Item = Result<Message, Status>> + Send + 'static {
        let (tx, rx) = mpsc::unbounded_channel::<Result<Message, Status>>();

        // Drain offline queue — discard anything older than OFFLINE_TTL_SECS
        let ttl = Duration::from_secs(OFFLINE_TTL_SECS);
        {
            let mut queue = self.offline_queue.lock().expect("offline_queue poisoned");
            if let Some(queued) = queue.remove(&process_id) {
                let now = Instant::now();
                for qm in queued {
                    if now.duration_since(qm.arrived_at) < ttl {
                        // Apply topic filter even for queued messages
                        if topics.is_empty() || topics.contains(&qm.msg.topic) {
                            let _ = tx.send(Ok(qm.msg));
                        }
                    }
                }
            }
        }

        // Register as active subscriber
        {
            let mut subs = self.subscribers.lock().expect("subscribers poisoned");
            subs.insert(
                process_id,
                SubscriberEntry { tx, topics },
            );
        }

        UnboundedReceiverStream::new(rx)
    }

    /// Unregister a subscriber (called when the gRPC stream closes).
    pub fn unsubscribe(&self, process_id: &str) {
        let mut subs = self.subscribers.lock().expect("subscribers poisoned");
        subs.remove(process_id);
    }

    // ── Send ──────────────────────────────────────────────────────────────────

    /// Route a message to `to_process_id`.
    ///
    /// Returns `(delivered, queued)`:
    /// - `delivered = true`  → active subscriber received it immediately
    /// - `queued    = true`  → no active subscriber; stored for later delivery
    /// - both `false`        → queue was full (message dropped)
    pub fn send(&self, msg: Message) -> (bool, bool) {
        let to = msg.to_process_id.clone();
        let topic = msg.topic.clone();

        // Try to deliver to active subscriber
        {
            let subs = self.subscribers.lock().expect("subscribers poisoned");
            if let Some(entry) = subs.get(&to) {
                let passes_filter = entry.topics.is_empty() || entry.topics.contains(&topic);
                if passes_filter {
                    match entry.tx.send(Ok(msg.clone())) {
                        Ok(_) => return (true, false),
                        Err(_) => {
                            // Channel closed — subscriber disconnected; fall through to queue
                            drop(subs);
                            // Remove stale entry (can't hold lock across the drop + re-lock)
                        }
                    }
                } else {
                    // Topic filtered out — silently drop (not delivered, not queued)
                    return (false, false);
                }
            }
        }

        // No active subscriber — enqueue for offline delivery
        let mut queue = self.offline_queue.lock().expect("offline_queue poisoned");
        let entry = queue.entry(to).or_insert_with(VecDeque::new);
        if entry.len() < MAX_OFFLINE_QUEUE {
            entry.push_back(QueuedMessage {
                msg,
                arrived_at: Instant::now(),
            });
            (false, true)
        } else {
            // Queue full — drop oldest, enqueue new
            entry.pop_front();
            entry.push_back(QueuedMessage {
                msg,
                arrived_at: Instant::now(),
            });
            (false, true)
        }
    }

    // ── Broadcast ─────────────────────────────────────────────────────────────

    /// Send `msg` to all active subscribers except `from_process_id`.
    ///
    /// Returns the number of processes that received the message immediately.
    pub fn broadcast(&self, msg: Message) -> u32 {
        let from = msg.from_process_id.clone();
        let topic = msg.topic.clone();
        let mut count = 0u32;

        let subs = self.subscribers.lock().expect("subscribers poisoned");
        for (pid, entry) in subs.iter() {
            if *pid == from {
                continue; // don't echo back to sender
            }
            let passes_filter = entry.topics.is_empty() || entry.topics.contains(&topic);
            if passes_filter {
                let clone = Message {
                    id: msg.id.clone(),
                    from_process_id: msg.from_process_id.clone(),
                    to_process_id: pid.clone(),
                    topic: msg.topic.clone(),
                    payload: msg.payload.clone(),
                    timestamp: msg.timestamp.clone(),
                };
                if entry.tx.send(Ok(clone)).is_ok() {
                    count += 1;
                }
            }
        }
        count
    }

    // ── Inspect ───────────────────────────────────────────────────────────────

    /// List process_ids with an active Subscribe stream.
    pub fn list_subscribers(&self) -> Vec<String> {
        let subs = self.subscribers.lock().expect("subscribers poisoned");
        subs.keys().cloned().collect()
    }
}
