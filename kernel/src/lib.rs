pub mod config;
pub mod daemon;
pub mod ipc;
pub mod orchestrator;
pub mod service;

pub const VERSION: &str = env!("CARGO_PKG_VERSION");

pub mod proto {
    tonic::include_proto!("vloop.kernel");
}
