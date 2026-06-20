use anyhow::{bail, Context, Result};
use std::path::{Path, PathBuf};

#[cfg(unix)]
use std::os::unix::fs::{FileTypeExt, PermissionsExt};

#[cfg(unix)]
use hyper_util::rt::TokioIo;
#[cfg(unix)]
use tokio::net::{UnixListener, UnixStream};
#[cfg(unix)]
use tonic::transport::{Channel, Endpoint, Uri};
#[cfg(unix)]
use tower::service_fn;

#[cfg(unix)]
pub async fn prepare_listener(socket_path: &Path) -> Result<UnixListener> {
    if let Some(parent) = socket_path.parent() {
        tokio::fs::create_dir_all(parent)
            .await
            .with_context(|| format!("failed to create {}", parent.display()))?;
    }

    if socket_path.exists() {
        let metadata = std::fs::symlink_metadata(socket_path)
            .with_context(|| format!("failed to inspect {}", socket_path.display()))?;
        let file_type = metadata.file_type();

        if file_type.is_symlink() {
            bail!(
                "refusing to reuse {} because it is a symlink",
                socket_path.display()
            );
        }
        if !file_type.is_socket() {
            bail!(
                "refusing to reuse {} because it is not a Unix socket",
                socket_path.display()
            );
        }

        match UnixStream::connect(socket_path).await {
            Ok(_) => bail!(
                "a VLoop daemon already appears to be listening on {}",
                socket_path.display()
            ),
            Err(_) => {
                tokio::fs::remove_file(socket_path).await.with_context(|| {
                    format!("failed to remove stale socket {}", socket_path.display())
                })?;
            }
        }
    }

    let listener = UnixListener::bind(socket_path)
        .with_context(|| format!("failed to bind {}", socket_path.display()))?;
    std::fs::set_permissions(socket_path, std::fs::Permissions::from_mode(0o600)).with_context(
        || {
            format!(
                "failed to restrict permissions on {}",
                socket_path.display()
            )
        },
    )?;
    Ok(listener)
}

#[cfg(unix)]
pub async fn connect_channel(socket_path: PathBuf) -> Result<Channel> {
    let endpoint = Endpoint::try_from("http://[::]:50051")?;
    let socket_path_for_error = socket_path.clone();
    let channel = endpoint
        .connect_with_connector(service_fn(move |_: Uri| {
            let socket_path = socket_path.clone();
            async move {
                let stream = UnixStream::connect(socket_path).await?;
                Ok::<_, std::io::Error>(TokioIo::new(stream))
            }
        }))
        .await
        .with_context(|| format!("failed to connect to {}", socket_path_for_error.display()))?;
    Ok(channel)
}

#[cfg(unix)]
pub async fn cleanup_socket(socket_path: &Path) -> Result<()> {
    match tokio::fs::remove_file(socket_path).await {
        Ok(_) => Ok(()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(error) => {
            Err(error).with_context(|| format!("failed to remove {}", socket_path.display()))
        }
    }
}

#[cfg(not(unix))]
pub async fn prepare_listener(_socket_path: &Path) -> Result<()> {
    bail!("Unix domain sockets are unavailable on this platform")
}

#[cfg(not(unix))]
pub async fn connect_channel(_socket_path: PathBuf) -> Result<()> {
    bail!("Unix domain sockets are unavailable on this platform")
}

#[cfg(not(unix))]
pub async fn cleanup_socket(_socket_path: &Path) -> Result<()> {
    Ok(())
}
