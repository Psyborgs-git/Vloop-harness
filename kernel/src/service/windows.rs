use super::{ServiceActionResult, ServiceDescriptor};

pub fn descriptor() -> ServiceDescriptor {
    ServiceDescriptor {
        platform: "windows".into(),
        label: "VLoopDaemon".into(),
        install_location: "Windows Service or Scheduled Task registration".into(),
        control_hint: "Use packaged installer integration for service registration.".into(),
        install_supported: false,
    }
}

pub fn install_service() -> ServiceActionResult {
    ServiceActionResult::unsupported(
        descriptor(),
        "Windows Service registration is deferred to the packaging stage; use `vloopctl start` during development.",
    )
}

pub fn uninstall_service() -> ServiceActionResult {
    ServiceActionResult::unsupported(
        descriptor(),
        "Windows Service removal is deferred to the packaging stage; stop the daemon with `vloopctl stop` during development.",
    )
}
