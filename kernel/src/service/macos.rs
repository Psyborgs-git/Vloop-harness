use super::{ServiceActionResult, ServiceDescriptor};

pub fn descriptor() -> ServiceDescriptor {
    ServiceDescriptor {
        platform: "macos".into(),
        label: "io.vloop.vloopd".into(),
        install_location: "~/Library/LaunchAgents/io.vloop.vloopd.plist".into(),
        control_hint: "launchctl bootstrap gui/<uid> ~/Library/LaunchAgents/io.vloop.vloopd.plist"
            .into(),
        install_supported: false,
    }
}

pub fn install_service() -> ServiceActionResult {
    ServiceActionResult::unsupported(
        descriptor(),
        "native LaunchAgent installation is deferred to the packaging stage; use `vloopctl start` during development.",
    )
}

pub fn uninstall_service() -> ServiceActionResult {
    ServiceActionResult::unsupported(
        descriptor(),
        "native LaunchAgent removal is deferred to the packaging stage; stop the daemon with `vloopctl stop` during development.",
    )
}
