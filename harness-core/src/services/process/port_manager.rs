use anyhow::Result;
use std::net::TcpListener;

/// Check if a port is available by attempting to bind to it.
pub fn is_port_available(port: u16) -> bool {
    TcpListener::bind(format!("127.0.0.1:{port}")).is_ok()
}

/// Find the first available port in [start, start+range).
pub fn find_free_port(start: u16, range: u16) -> Option<u16> {
    (start..start + range).find(|&p| is_port_available(p))
}
