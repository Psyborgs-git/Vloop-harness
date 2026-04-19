use anyhow::{anyhow, Result};
use dashmap::DashMap;
use std::{collections::HashMap, sync::Arc};
use uuid::Uuid;

use crate::commands::terminal::TerminalSessionInfo;

use super::session::PtySession;

pub struct TerminalManager {
    sessions: Arc<DashMap<String, PtySession>>,
    app_handle: tauri::AppHandle,
}

impl TerminalManager {
    pub fn new(app_handle: tauri::AppHandle) -> Self {
        Self {
            sessions: Arc::new(DashMap::new()),
            app_handle,
        }
    }

    pub async fn create_session(
        &self,
        shell: String,
        cwd: String,
        env: HashMap<String, String>,
    ) -> Result<String> {
        let id = Uuid::new_v4().to_string();
        let session = PtySession::new(id.clone(), shell, cwd, env, self.app_handle.clone())?;
        self.sessions.insert(id.clone(), session);
        Ok(id)
    }

    pub async fn write_to_session(&self, session_id: &str, data: &[u8]) -> Result<()> {
        let session = self
            .sessions
            .get(session_id)
            .ok_or_else(|| anyhow!("Session not found: {}", session_id))?;
        session.write(data)
    }

    pub async fn resize_session(&self, session_id: &str, cols: u16, rows: u16) -> Result<()> {
        let session = self
            .sessions
            .get(session_id)
            .ok_or_else(|| anyhow!("Session not found: {}", session_id))?;
        session.resize(cols, rows)
    }

    pub async fn kill_session(&self, session_id: &str) -> Result<()> {
        self.sessions
            .remove(session_id)
            .ok_or_else(|| anyhow!("Session not found: {}", session_id))?;
        Ok(())
    }

    pub fn list_sessions(&self) -> Vec<TerminalSessionInfo> {
        self.sessions
            .iter()
            .map(|s| TerminalSessionInfo {
                id: s.id.clone(),
                shell: s.shell.clone(),
                cwd: s.cwd.clone(),
                pid: s.pid,
                status: s.status.clone(),
            })
            .collect()
    }
}
