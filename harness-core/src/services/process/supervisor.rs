use anyhow::Result;
use parking_lot::Mutex;
use std::{
    collections::VecDeque,
    io::{BufRead, BufReader},
    process::{Child, Command, Stdio},
    sync::Arc,
    thread,
};
use tauri::Emitter;

use crate::commands::process::{ProcessInfo, ProcessLog};

pub struct SupervisedProcess {
    pub id: String,
    pub name: String,
    pub command: String,
    pub args: Vec<String>,
    pub status: String,
    pub pid: Option<u32>,
    pub port: Option<u16>,
    pub started_at: Option<String>,
    logs: Arc<Mutex<VecDeque<ProcessLog>>>,
    child: Arc<Mutex<Option<Child>>>,
}

impl SupervisedProcess {
    pub fn new(
        id: String,
        name: String,
        command: String,
        args: Vec<String>,
        cwd: Option<String>,
        env: Option<std::collections::HashMap<String, String>>,
        port: Option<u16>,
        app_handle: tauri::AppHandle,
    ) -> Result<Self> {
        let logs: Arc<Mutex<VecDeque<ProcessLog>>> =
            Arc::new(Mutex::new(VecDeque::with_capacity(1000)));

        let mut cmd = Command::new(&command);
        cmd.args(&args)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        if let Some(cwd) = cwd {
            cmd.current_dir(cwd);
        }
        if let Some(env) = env {
            for (k, v) in env {
                cmd.env(k, v);
            }
        }

        let mut child = cmd.spawn()?;
        let pid = child.id();

        let spawn_pipe = |stream: String,
                          reader: Box<dyn std::io::Read + Send>,
                          logs_c: Arc<Mutex<VecDeque<ProcessLog>>>,
                          id_c: String,
                          handle_c: tauri::AppHandle| {
            thread::spawn(move || {
                let reader = BufReader::new(reader);
                for line in reader.lines().flatten() {
                    let ts = chrono::Utc::now().to_rfc3339();
                    let entry = ProcessLog {
                        process_id: id_c.clone(),
                        stream: stream.clone(),
                        line: line.clone(),
                        ts: ts.clone(),
                    };
                    let mut guard = logs_c.lock();
                    if guard.len() >= 1000 {
                        guard.pop_front();
                    }
                    guard.push_back(entry);
                    let _ = handle_c.emit(
                        "process_log",
                        serde_json::json!({
                            "id": id_c, "stream": stream, "line": line, "ts": ts
                        }),
                    );
                }
            });
        };

        if let Some(stdout) = child.stdout.take() {
            spawn_pipe(
                "stdout".into(),
                Box::new(stdout),
                logs.clone(),
                id.clone(),
                app_handle.clone(),
            );
        }
        if let Some(stderr) = child.stderr.take() {
            spawn_pipe(
                "stderr".into(),
                Box::new(stderr),
                logs.clone(),
                id.clone(),
                app_handle.clone(),
            );
        }

        let started_at = Some(chrono::Utc::now().to_rfc3339());
        Ok(Self {
            id,
            name,
            command,
            args,
            status: "running".into(),
            pid: Some(pid),
            port,
            started_at,
            logs,
            child: Arc::new(Mutex::new(Some(child))),
        })
    }

    pub fn stop(&mut self) -> Result<()> {
        if let Some(child) = self.child.lock().as_mut() {
            child.kill().ok();
        }
        self.status = "stopped".into();
        Ok(())
    }

    pub fn logs(&self, limit: usize) -> Vec<ProcessLog> {
        let guard = self.logs.lock();
        guard
            .iter()
            .rev()
            .take(limit)
            .cloned()
            .collect::<Vec<_>>()
            .into_iter()
            .rev()
            .collect()
    }

    pub fn to_info(&self) -> ProcessInfo {
        ProcessInfo {
            id: self.id.clone(),
            name: self.name.clone(),
            command: self.command.clone(),
            status: self.status.clone(),
            pid: self.pid,
            port: self.port,
            started_at: self.started_at.clone(),
        }
    }
}
