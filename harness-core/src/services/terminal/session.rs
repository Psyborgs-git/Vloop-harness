use anyhow::{anyhow, Result};
use portable_pty::{native_pty_system, CommandBuilder, MasterPty, PtySize};
use std::{
    collections::HashMap,
    io::{Read, Write},
    sync::{Arc, Mutex},
};
use tauri::Emitter;
use uuid::Uuid;

pub struct PtySession {
    pub id: String,
    pub shell: String,
    pub cwd: String,
    pub pid: Option<u32>,
    pub status: String,
    master: Arc<Mutex<Box<dyn MasterPty + Send>>>,
    writer: Arc<Mutex<Box<dyn Write + Send>>>,
}

impl PtySession {
    pub fn new(
        id: String,
        shell: String,
        cwd: String,
        env: HashMap<String, String>,
        app_handle: tauri::AppHandle,
    ) -> Result<Self> {
        let pty_system = native_pty_system();
        let pair = pty_system
            .openpty(PtySize {
                rows: 24,
                cols: 80,
                pixel_width: 0,
                pixel_height: 0,
            })
            .map_err(|e| anyhow!("PTY open failed: {e}"))?;

        let mut cmd = CommandBuilder::new(&shell);
        cmd.cwd(&cwd);
        for (k, v) in &env {
            cmd.env(k, v);
        }

        let child = pair
            .slave
            .spawn_command(cmd)
            .map_err(|e| anyhow!("Spawn failed: {e}"))?;
        let pid = child.process_id();

        let writer = pair
            .master
            .take_writer()
            .map_err(|e| anyhow!("Writer: {e}"))?;
        let master = Arc::new(Mutex::new(pair.master));
        let writer = Arc::new(Mutex::new(writer));

        // Async read loop
        let mut reader = {
            let m = master.lock().unwrap();
            m.try_clone_reader()
                .map_err(|e| anyhow!("Reader clone: {e}"))?
        };
        let id_clone = id.clone();
        std::thread::spawn(move || {
            let mut buf = [0u8; 4096];
            loop {
                match reader.read(&mut buf) {
                    Ok(0) | Err(_) => break,
                    Ok(n) => {
                        let data = String::from_utf8_lossy(&buf[..n]).to_string();
                        let _ = app_handle.emit(
                            "terminal_output",
                            serde_json::json!({ "session_id": id_clone, "data": data }),
                        );
                    }
                }
            }
        });

        Ok(Self {
            id,
            shell,
            cwd,
            pid,
            status: "running".into(),
            master,
            writer,
        })
    }

    pub fn write(&self, data: &[u8]) -> Result<()> {
        self.writer
            .lock()
            .unwrap()
            .write_all(data)
            .map_err(|e| anyhow!("Write error: {e}"))
    }

    pub fn resize(&self, cols: u16, rows: u16) -> Result<()> {
        self.master
            .lock()
            .unwrap()
            .resize(PtySize {
                rows,
                cols,
                pixel_width: 0,
                pixel_height: 0,
            })
            .map_err(|e| anyhow!("Resize error: {e}"))
    }
}
