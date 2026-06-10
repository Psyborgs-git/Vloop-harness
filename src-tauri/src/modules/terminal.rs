use std::collections::HashMap;
use std::io::{Read, Write};
use std::path::PathBuf;
use std::sync::{Arc, Mutex};

use portable_pty::{CommandBuilder, NativePtySystem, PtySize, PtySystem};
use serde::{Deserialize, Serialize};
use serde_json::json;
use tokio::sync::mpsc;

// -- Traits and core structs

pub trait TerminalSessionTransport: Send + Sync {
    fn write_stdin(&mut self, data: &[u8]) -> Result<(), String>;
    fn kill(&mut self) -> Result<(), String>;
    fn resize(&mut self, rows: u16, cols: u16) -> Result<(), String>;
}

pub struct TerminalSession {
    pub session_id: String,
    transport: Arc<Mutex<Box<dyn TerminalSessionTransport>>>,
    output_tx: mpsc::Sender<Vec<u8>>,
    buffer: Arc<Mutex<Vec<u8>>>, // Recent buffer
}

#[derive(Serialize, Deserialize, Clone)]
pub struct LocalTerminalOptions {
    pub cwd: PathBuf,
    pub command: String,
    pub args: Vec<String>,
}

pub struct LocalTerminalTransport {
    pty_writer: Mutex<Box<dyn Write + Send>>,
    child: Mutex<Box<dyn portable_pty::Child + Send>>,
}

impl TerminalSessionTransport for LocalTerminalTransport {
    fn write_stdin(&mut self, data: &[u8]) -> Result<(), String> {
        let mut writer = self.pty_writer.lock().unwrap();
        writer
            .write_all(data)
            .map_err(|e| format!("Failed to write to pty: {}", e))?;
        writer.flush().map_err(|e| format!("Failed to flush pty: {}", e))
    }

    fn kill(&mut self) -> Result<(), String> {
        let mut child = self.child.lock().unwrap();
        child.kill().map_err(|e| format!("Failed to kill child process: {}", e))
    }

    fn resize(&mut self, _rows: u16, _cols: u16) -> Result<(), String> {
        // Implement resize via pty master
        Ok(())
    }
}

// Global registry
lazy_static::lazy_static! {
    static ref SESSIONS: Mutex<HashMap<String, TerminalSession>> = Mutex::new(HashMap::new());
}

pub async fn start_local_session(
    session_id: String,
    cwd: PathBuf,
    command: String,
    args: Vec<String>,
    log_dir: PathBuf,
) -> Result<(), String> {
    let pty_system = NativePtySystem::default();
    let pair = pty_system
        .openpty(PtySize {
            rows: 24,
            cols: 80,
            pixel_width: 0,
            pixel_height: 0,
        })
        .map_err(|e| format!("Failed to open pty: {}", e))?;

    let mut cmd = CommandBuilder::new(&command);
    cmd.args(&args);
    cmd.cwd(cwd);

    let child = pair
        .slave
        .spawn_command(cmd)
        .map_err(|e| format!("Failed to spawn command: {}", e))?;

    let mut reader = pair
        .master
        .try_clone_reader()
        .map_err(|e| format!("Failed to clone reader: {}", e))?;

    // Create channel for output processing
    let (tx, mut rx) = mpsc::channel::<Vec<u8>>(1024);

    let buffer = Arc::new(Mutex::new(Vec::new()));
    let buffer_clone = buffer.clone();

    let log_file_path = log_dir.join("log.jsonl");
    std::fs::create_dir_all(&log_dir).unwrap_or_default();

    // Spawn task to read from PTY and send to channel
    tokio::task::spawn_blocking(move || {
        let mut buf = [0u8; 4096];
        loop {
            match reader.read(&mut buf) {
                Ok(0) => break, // EOF
                Ok(n) => {
                    let data = buf[..n].to_vec();
                    if tx.blocking_send(data).is_err() {
                        break;
                    }
                }
                Err(_) => break,
            }
        }
    });

    // Spawn task to handle output stream (update buffer and write to log)
    tokio::spawn(async move {
        use tokio::fs::OpenOptions;
        use tokio::io::AsyncWriteExt;

        let mut file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&log_file_path)
            .await;

        while let Some(data) = rx.recv().await {
            // Update in-memory buffer (keep last N bytes)
            {
                let mut buf = buffer_clone.lock().unwrap();
                buf.extend_from_slice(&data);
                if buf.len() > 1024 * 1024 {
                    // Limit to 1MB
                    let truncate_len = buf.len() - 1024 * 1024;
                    buf.drain(0..truncate_len);
                }
            }

            // Write to JSONL
            if let Ok(ref mut f) = file {
                let text = String::from_utf8_lossy(&data).into_owned();
                let log_entry = json!({
                    "timestamp": std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs_f64()).unwrap_or(0.0),
                    "output": text
                });
                let mut line = log_entry.to_string();
                line.push('\n');
                let _ = f.write_all(line.as_bytes()).await;
            }
        }
    });

    let writer = pair.master.take_writer().map_err(|e| format!("Failed to take writer: {}", e))?;

    let transport = LocalTerminalTransport {
        pty_writer: Mutex::new(writer),
        child: Mutex::new(child),
    };

    let session = TerminalSession {
        session_id: session_id.clone(),
        transport: Arc::new(Mutex::new(Box::new(transport))),
        // Use a dummy sender since the real one moved to the reader task,
        // we won't need to send *from* the struct, just hold the buffer.
        output_tx: mpsc::channel(1).0,
        buffer,
    };

    SESSIONS.lock().unwrap().insert(session_id, session);
    Ok(())
}

pub fn send_keys(session_id: &str, keys: &str) -> Result<(), String> {
    let mut sessions = SESSIONS.lock().unwrap();
    if let Some(session) = sessions.get_mut(session_id) {
        let mut transport = session.transport.lock().unwrap();
        transport.write_stdin(keys.as_bytes())?;
        Ok(())
    } else {
        Err(format!("Session {} not found", session_id))
    }
}

pub fn read_buffer(session_id: &str) -> Result<String, String> {
    let sessions = SESSIONS.lock().unwrap();
    if let Some(session) = sessions.get(session_id) {
        let mut buffer = session.buffer.lock().unwrap();
        let res = String::from_utf8_lossy(&buffer).into_owned();
        buffer.clear(); // Consume buffer
        Ok(res)
    } else {
        Err(format!("Session {} not found", session_id))
    }
}

pub fn close_session(session_id: &str) -> Result<(), String> {
    let session = {
        let mut sessions = SESSIONS.lock().unwrap();
        sessions.remove(session_id)
    };
    if let Some(session) = session {
        let mut transport = session.transport.lock().unwrap();
        let _ = transport.kill();
        Ok(())
    } else {
        Err(format!("Session {} not found", session_id))
    }
}
