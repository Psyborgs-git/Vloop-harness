use super::{ServiceActionResult, ServiceDescriptor};

pub fn descriptor() -> ServiceDescriptor {
    ServiceDescriptor {
        platform: "linux".into(),
        label: "vloopd.service".into(),
        install_location: "~/.config/systemd/user/vloopd.service".into(),
        control_hint: "systemctl --user enable --now vloopd.service".into(),
        install_supported: false,
    }
}

pub fn install_service() -> ServiceActionResult {
    ServiceActionResult::unsupported(
        descriptor(),
        "systemd user-service installation is deferred to the packaging stage; use `vloopctl start` during development.",
    )
}

pub fn uninstall_service() -> ServiceActionResult {
    ServiceActionResult::unsupported(
        descriptor(),
        "systemd user-service removal is deferred to the packaging stage; stop the daemon with `vloopctl stop` during development.",
    )
}
