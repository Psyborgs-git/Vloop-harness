use std::process::{Child, Command, Stdio};
use std::time::Duration;
use std::path::{Path, PathBuf};
use crate::fs;
use crate::rpc::system::{system_control_client::SystemControlClient, HeartbeatRequest};
#[cfg(unix)]
use hyper_util::rt::TokioIo;

fn find_control_plane_dir() -> PathBuf {
    // Start from current working directory
    let mut dir = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    
    // Walk up to find the folder containing "control-plane"
    for _ in 0..10 {
        let cp_path = dir.join("control-plane");
        if cp_path.is_dir() && cp_path.join("main.py").is_file() {
            println!("Found control-plane at: {:?}", cp_path);
            return cp_path;
        }
        if let Some(parent) = dir.parent() {
            dir = parent.to_path_buf();
        } else {
            break;
        }
    }
    
    // Fallback to sibling of src-tauri
    PathBuf::from("../control-plane")
}

pub fn start_python_supervisor() -> Child {
    println!("Starting Python Control Plane Supervisor...");
    let cp_dir = find_control_plane_dir();

    // Try executing 'uv', fallback to direct 'python main.py' or 'python3 main.py' in the virtualenv if available
    let mut cmd = Command::new("uv");
    cmd.arg("run")
       .arg("python")
       .arg("main.py")
       .current_dir(&cp_dir)
       .stdout(Stdio::inherit())
       .stderr(Stdio::inherit());

    match cmd.spawn() {
        Ok(child) => {
            println!("Python Control Plane started with PID: {}", child.id());
            child
        }
        Err(e) => {
            eprintln!("Failed to spawn Python Control Plane with 'uv': {}. Trying backup 'python3 main.py'...", e);
            
            // Backup: Try finding .venv/bin/python or fallback to python3
            let venv_python = cp_dir.join(".venv").join("bin").join("python");
            let python_bin = if venv_python.is_file() {
                venv_python.to_string_lossy().into_owned()
            } else {
                "python3".to_string()
            };

            Command::new(python_bin)
                .arg("main.py")
                .current_dir(&cp_dir)
                .stdout(Stdio::inherit())
                .stderr(Stdio::inherit())
                .spawn()
                .expect("Failed to start Python Control Plane. Ensure python3 is installed and accessible.")
        }
    }
}

#[allow(clippy::zombie_processes)]
pub fn start_watchdog() {
    let mut child = start_python_supervisor();

    tokio::spawn(async move {
        // Wait for python server to boot
        tokio::time::sleep(Duration::from_secs(1)).await;

        let vloop_home = fs::get_vloop_home().unwrap();
        let socket_path = vloop_home.join("rust").join("ipc.sock");

        let mut channel = None;
        for i in 1..=15 {
            #[cfg(unix)]
            let chan = {
                let path = socket_path.clone();
                tonic::transport::Endpoint::try_from("http://[::]:50051")
                    .unwrap()
                    .connect_with_connector(tower::service_fn(move |_: tonic::transport::Uri| {
                        let path = path.clone();
                        async move {
                            Ok::<_, std::io::Error>(TokioIo::new(
                                tokio::net::UnixStream::connect(path).await?
                            ))
                        }
                    }))
                    .await
            };

            #[cfg(not(unix))]
            let chan = tonic::transport::Endpoint::try_from("http://127.0.0.1:50051")
                .unwrap()
                .connect()
                .await;

            match chan {
                Ok(c) => {
                    println!("Successfully connected to Python Control Plane over IPC on attempt {}.", i);
                    channel = Some(c);
                    break;
                }
                Err(_) => {
                    tokio::time::sleep(Duration::from_secs(1)).await;
                }
            }
        }

        if let Some(channel) = channel {
            let mut client = SystemControlClient::new(channel);
            let mut missed_pings = 0;

            loop {
                tokio::time::sleep(Duration::from_secs(5)).await;

                let request = tonic::Request::new(HeartbeatRequest {
                    timestamp: chrono::Utc::now().timestamp(),
                    status: "Ping".into(),
                });

                match client.heartbeat(request).await {
                    Ok(_) => {
                        missed_pings = 0;
                        // println!("Heartbeat ACK");
                    }
                    Err(e) => {
                        missed_pings += 1;
                        eprintln!("Heartbeat failed ({} / 3): {}", missed_pings, e);

                        if missed_pings >= 3 {
                            eprintln!("CRITICAL: Control Plane Deadlock Detected. Restarting...");
                            let _ = child.kill();
                            let _ = child.wait();
                            
                            // Restart
                            child = start_python_supervisor();
                            missed_pings = 0;
                            // Need to wait for reboot
                            tokio::time::sleep(Duration::from_secs(3)).await;
                        }
                    }
                }
            }
        } else {
            eprintln!("Failed to connect to Python Control Plane over IPC after 15 attempts.");
        }
    });
}
