use anyhow::{bail, Context, Result};
use serde::Deserialize;
use std::{process::Output, time::Duration};
use tokio::{process::Command, time::sleep};
use vloop_kernel::{daemon, service};

const LAUNCH_WAIT_TIMEOUT: Duration = Duration::from_secs(15);
const POLL_INTERVAL: Duration = Duration::from_millis(750);

#[derive(Debug, Deserialize)]
struct LauncherStatus {
    daemon_reachable: bool,
    health: String,
    status_message: String,
}

#[tokio::main]
async fn main() -> Result<()> {
    daemon::init_tracing();
    let exit_code = run().await?;
    std::process::exit(exit_code);
}

async fn run() -> Result<i32> {
    let vloopctl = service::sibling_binary("vloopctl")?;
    if !vloopctl.is_file() {
        bail!(
            "could not find sibling vloopctl binary at {}",
            vloopctl.display()
        );
    }

    let initial_status = read_status(&vloopctl).await?;
    if initial_status
        .as_ref()
        .map(|status| !status.daemon_reachable)
        .unwrap_or(true)
    {
        let output = run_vloopctl(&vloopctl, &["start", "--json"]).await?;
        if !output.status.success() {
            eprintln!("failed to start vloopd through vloopctl");
            print_output(&output);
            return handoff_to_doctor(&vloopctl).await;
        }
    }

    let deadline = tokio::time::Instant::now() + LAUNCH_WAIT_TIMEOUT;
    loop {
        if let Some(status) = read_status(&vloopctl).await? {
            if !status.daemon_reachable {
                if tokio::time::Instant::now() >= deadline {
                    eprintln!("VLoop did not expose live kernel status in time.");
                    return handoff_to_doctor(&vloopctl).await;
                }
                sleep(POLL_INTERVAL).await;
                continue;
            }

            match status.health.as_str() {
                "ready" => {
                    let output = run_vloopctl(&vloopctl, &["open-ui", "--json"]).await?;
                    if output.status.success() {
                        return Ok(0);
                    }

                    eprintln!(
                        "VLoop is running, but the UI could not be opened: {}",
                        status.status_message
                    );
                    print_output(&output);
                    return handoff_to_doctor(&vloopctl).await;
                }
                "dependency_missing" => {
                    eprintln!(
                        "VLoop cannot finish launching because required dependencies are missing: {}",
                        status.status_message
                    );
                    return handoff_to_doctor(&vloopctl).await;
                }
                "starting" | "cp_unregistered" | "cp_restarting" => {
                    if tokio::time::Instant::now() >= deadline {
                        eprintln!(
                            "VLoop is still starting, but it did not become ready in time: {}",
                            status.status_message
                        );
                        return handoff_to_doctor(&vloopctl).await;
                    }
                    sleep(POLL_INTERVAL).await;
                }
                _ => {
                    eprintln!(
                        "VLoop did not reach a usable state: {} ({})",
                        status.health, status.status_message
                    );
                    return handoff_to_doctor(&vloopctl).await;
                }
            }
        } else if tokio::time::Instant::now() >= deadline {
            eprintln!("VLoop did not expose kernel status in time.");
            return handoff_to_doctor(&vloopctl).await;
        } else {
            sleep(POLL_INTERVAL).await;
        }
    }
}

async fn read_status(vloopctl: &std::path::Path) -> Result<Option<LauncherStatus>> {
    let output = run_vloopctl(vloopctl, &["status", "--json"]).await?;
    let stdout = String::from_utf8_lossy(&output.stdout);

    if stdout.trim().is_empty() {
        return Ok(None);
    }

    match serde_json::from_str::<LauncherStatus>(&stdout) {
        Ok(status) => Ok(Some(status)),
        Err(_) => Ok(None),
    }
}

async fn handoff_to_doctor(vloopctl: &std::path::Path) -> Result<i32> {
    let output = run_vloopctl(vloopctl, &["doctor"]).await?;
    print_output(&output);
    Ok(output.status.code().unwrap_or(1))
}

async fn run_vloopctl(vloopctl: &std::path::Path, args: &[&str]) -> Result<Output> {
    Command::new(vloopctl)
        .args(args)
        .output()
        .await
        .with_context(|| format!("failed to run {}", vloopctl.display()))
}

fn print_output(output: &Output) {
    let stdout = String::from_utf8_lossy(&output.stdout);
    if !stdout.trim().is_empty() {
        println!("{}", stdout.trim_end());
    }

    let stderr = String::from_utf8_lossy(&output.stderr);
    if !stderr.trim().is_empty() {
        eprintln!("{}", stderr.trim_end());
    }
}
