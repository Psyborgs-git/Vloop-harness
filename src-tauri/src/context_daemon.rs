use notify::{Config, RecommendedWatcher, RecursiveMode, Watcher};
use std::path::Path;
use std::fs;
use crate::rpc::system::{system_control_client::SystemControlClient, IngestRequest};
#[cfg(unix)]
use hyper_util::rt::TokioIo;
use crate::fs as vloop_fs;

pub fn start_context_daemon() {
    tokio::spawn(async move {
        println!("Starting Background RAG Context Daemon...");
        
        let vloop_home = vloop_fs::get_vloop_home().unwrap();
        let watch_dir = vloop_home.join("workspace");
        std::fs::create_dir_all(&watch_dir).unwrap_or_default();
        
        let socket_path = vloop_home.join("rust").join("ipc.sock");

        let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel();
        
        // notify requires a sync closure/callback, so we use unbounded_send
        #[allow(clippy::collapsible_if)]
        let mut watcher = match RecommendedWatcher::new(move |res: notify::Result<notify::Event>| {
            if let Ok(event) = res {
                if event.kind.is_modify() || event.kind.is_create() {
                    for path in event.paths {
                        if path.is_file() {
                            if let Some(ext) = path.extension() {
                                if ext == "txt" || ext == "md" || ext == "py" || ext == "js" || ext == "rs" {
                                    let _ = tx.send(path);
                                }
                            }
                        }
                    }
                }
            }
        }, Config::default()) {
            Ok(w) => w,
            Err(e) => {
                eprintln!("Failed to create watcher: {:?}", e);
                return;
            }
        };

        if let Err(e) = watcher.watch(Path::new(&watch_dir), RecursiveMode::Recursive) {
            eprintln!("Failed to watch directory: {:?}", e);
            return;
        }

        while let Some(path) = rx.recv().await {
            // Read file content
            if let Ok(content) = fs::read_to_string(&path) {
                // Connect to Python IPC
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
                    let request = tonic::Request::new(IngestRequest {
                        file_path: path.to_string_lossy().into_owned(),
                        content,
                    });
                    let _ = client.ingest_document(request).await;
                }
            }
        }
    });
}
