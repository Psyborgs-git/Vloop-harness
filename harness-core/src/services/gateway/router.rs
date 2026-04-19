// Round-robin router (future extension point)
use crate::services::gateway::channel::Channel;
use std::sync::Arc;

pub struct Router {
    adapters: Vec<Arc<Box<dyn Channel>>>,
    next: std::sync::atomic::AtomicUsize,
}

impl Router {
    pub fn new(adapters: Vec<Arc<Box<dyn Channel>>>) -> Self {
        Self {
            adapters,
            next: std::sync::atomic::AtomicUsize::new(0),
        }
    }

    pub fn next_adapter(&self) -> Option<&Box<dyn Channel>> {
        if self.adapters.is_empty() {
            return None;
        }
        let idx = self
            .next
            .fetch_add(1, std::sync::atomic::Ordering::Relaxed)
            % self.adapters.len();
        Some(&self.adapters[idx])
    }
}
