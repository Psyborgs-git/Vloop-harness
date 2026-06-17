use std::process::{Child, Command, Stdio};
use std::time::Duration;
use crate::fs;
use crate::rpc::system::{system_control_client::SystemControlClient, HeartbeatRequest};
#[cfg(unix)]
use hyper_util::rt::TokioIo;

pub fn start_python_supervisor() -> Child {
    println!("Starting Python Control Plane Supervisor...");

    let child = Command::new("uv")
        .arg("run")
        .arg("python")
        .arg("main.py")
        .current_dir("../control-plane")
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .spawn()
        .expect("Failed to start Python Control Plane. Is 'uv' installed?");

    println!("Python Control Plane started with PID: {}", child.id());
    child
}

pub fn start_watchdog() {
    let mut child = start_python_supervisor();

    tokio::spawn(async move {
        // Wait for python server to boot
        tokio::time::sleep(Duration::from_secs(3)).await;

        let vloop_home = fs::get_vloop_home().unwrap();
        let socket_path = vloop_home.join("rust").join("ipc.sock");

        #[cfg(unix)]
        let channel = {
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
        let channel = tonic::transport::Endpoint::try_from("http://127.0.0.1:50051")
            .unwrap()
            .connect()
            .await;

        if let Ok(channel) = channel {
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
            eprintln!("Failed to connect to Python Control Plane over IPC.");
        }
    });
}
