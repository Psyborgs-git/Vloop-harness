use std::fs;
use std::path::Path;
use std::time::SystemTime;
use crate::fs as vloop_fs;

/// Checks and performs bi-directional synchronization of the SQLite databases
/// between the local VLoop directory and a simulated remote cloud-sync/S3 bucket.
pub fn sync_databases() {
    println!("[LITEFS SYNC] Initiating database synchronization...");

    let vloop_home = match vloop_fs::get_vloop_home() {
        Some(path) => path,
        None => {
            eprintln!("[LITEFS SYNC] Error: Could not determine VLoop home directory.");
            return;
        }
    };

    let db_dir = vloop_home.join("db");
    if !db_dir.exists() {
        if let Err(e) = fs::create_dir_all(&db_dir) {
            eprintln!("[LITEFS SYNC] Error: Failed to create database directory: {:?}", e);
            return;
        }
    }

    // Define the simulated cloud storage / S3 sync bucket directory.
    // In a real S3 backup, this would upload to S3; for local-first sync, we use a dedicated sync directory
    // representing the configured S3 / cloud-synced boundary (e.g., ~/.vloop_cloud_sync).
    let mut cloud_sync_dir = dirs::home_dir().expect("Could not determine home directory");
    cloud_sync_dir.push(".vloop_cloud_sync");
    
    if !cloud_sync_dir.exists() {
        if let Err(e) = fs::create_dir_all(&cloud_sync_dir) {
            eprintln!("[LITEFS SYNC] Error: Failed to create cloud sync directory: {:?}", e);
            return;
        }
    }

    let databases = vec!["workflows.sqlite", "vloop.sqlite"];

    for db_name in databases {
        let local_path = db_dir.join(db_name);
        let remote_path = cloud_sync_dir.join(db_name);

        sync_file(&local_path, &remote_path);
    }
    
    println!("[LITEFS SYNC] Database synchronization completed.");
}

fn sync_file(local: &Path, remote: &Path) {
    let local_exists = local.exists();
    let remote_exists = remote.exists();

    match (local_exists, remote_exists) {
        (true, true) => {
            // Compare modification times
            let local_mtime = get_modified_time(local).unwrap_or(SystemTime::UNIX_EPOCH);
            let remote_mtime = get_modified_time(remote).unwrap_or(SystemTime::UNIX_EPOCH);

            if remote_mtime > local_mtime {
                println!("[LITEFS SYNC] Remote version of {:?} is newer. Pulling from cloud...", local.file_name().unwrap());
                if let Err(e) = fs::copy(remote, local) {
                    eprintln!("[LITEFS SYNC] Error pulling file: {:?}", e);
                }
            } else if local_mtime > remote_mtime {
                println!("[LITEFS SYNC] Local version of {:?} is newer. Pushing to cloud...", local.file_name().unwrap());
                if let Err(e) = fs::copy(local, remote) {
                    eprintln!("[LITEFS SYNC] Error pushing file: {:?}", e);
                }
            }
        }
        (true, false) => {
            println!("[LITEFS SYNC] No remote copy found for {:?}. Pushing to cloud...", local.file_name().unwrap());
            if let Err(e) = fs::copy(local, remote) {
                eprintln!("[LITEFS SYNC] Error pushing new file: {:?}", e);
            }
        }
        (false, true) => {
            println!("[LITEFS SYNC] No local copy found for {:?}. Pulling from cloud...", local.file_name().unwrap());
            if let Err(e) = fs::copy(remote, local) {
                eprintln!("[LITEFS SYNC] Error pulling new file: {:?}", e);
            }
        }
        (false, false) => {
            // Nothing to sync yet
        }
    }
}

fn get_modified_time(path: &Path) -> Option<SystemTime> {
    fs::metadata(path).and_then(|meta| path_mtime(&meta)).ok()
}

fn path_mtime(meta: &fs::Metadata) -> std::io::Result<SystemTime> {
    meta.modified()
}

/// Spawns a background thread to continuously sync database state asynchronously (LiteFS replication).
pub fn start_litefs_sync_daemon() {
    tokio::spawn(async move {
        println!("Starting Background LiteFS SQLite Replication Daemon...");
        loop {
            tokio::time::sleep(std::time::Duration::from_secs(10)).await;
            sync_databases();
        }
    });
}
