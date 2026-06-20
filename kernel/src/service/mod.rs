pub mod linux;
pub mod macos;
pub mod windows;

use anyhow::{Context, Result};
use serde::Serialize;
use std::path::PathBuf;

#[derive(Debug, Clone, Serialize)]
pub struct ServiceDescriptor {
    pub platform: String,
    pub label: String,
    pub install_location: String,
    pub control_hint: String,
    pub install_supported: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct ServiceActionResult {
    pub success: bool,
    pub message: String,
    pub descriptor: ServiceDescriptor,
}

impl ServiceActionResult {
    pub fn unsupported(descriptor: ServiceDescriptor, message: impl Into<String>) -> Self {
        Self {
            success: false,
            message: message.into(),
            descriptor,
        }
    }

    pub fn success(descriptor: ServiceDescriptor, message: impl Into<String>) -> Self {
        Self {
            success: true,
            message: message.into(),
            descriptor,
        }
    }
}

pub fn descriptor() -> ServiceDescriptor {
    #[cfg(target_os = "macos")]
    {
        return macos::descriptor();
    }

    #[cfg(target_os = "linux")]
    {
        return linux::descriptor();
    }

    #[cfg(target_os = "windows")]
    {
        return windows::descriptor();
    }

    #[allow(unreachable_code)]
    ServiceDescriptor {
        platform: std::env::consts::OS.into(),
        label: "vloopd".into(),
        install_location: "unsupported".into(),
        control_hint: "unsupported".into(),
        install_supported: false,
    }
}

pub fn install_service() -> Result<ServiceActionResult> {
    #[cfg(target_os = "macos")]
    {
        return Ok(macos::install_service());
    }

    #[cfg(target_os = "linux")]
    {
        return Ok(linux::install_service());
    }

    #[cfg(target_os = "windows")]
    {
        return Ok(windows::install_service());
    }

    #[allow(unreachable_code)]
    Ok(ServiceActionResult::unsupported(
        descriptor(),
        "native service installation is not supported on this platform",
    ))
}

pub fn uninstall_service() -> Result<ServiceActionResult> {
    #[cfg(target_os = "macos")]
    {
        return Ok(macos::uninstall_service());
    }

    #[cfg(target_os = "linux")]
    {
        return Ok(linux::uninstall_service());
    }

    #[cfg(target_os = "windows")]
    {
        return Ok(windows::uninstall_service());
    }

    #[allow(unreachable_code)]
    Ok(ServiceActionResult::unsupported(
        descriptor(),
        "native service removal is not supported on this platform",
    ))
}

pub fn sibling_binary(name: &str) -> Result<PathBuf> {
    let current_exe =
        std::env::current_exe().context("failed to resolve current executable path")?;
    let parent = current_exe
        .parent()
        .context("current executable did not have a parent directory")?;

    #[cfg(windows)]
    let candidate = parent.join(format!("{name}.exe"));
    #[cfg(not(windows))]
    let candidate = parent.join(name);

    Ok(candidate)
}
