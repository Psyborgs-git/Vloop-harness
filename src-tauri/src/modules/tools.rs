use std::collections::{HashMap, HashSet};
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex, OnceLock};
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use serde::{Deserialize, Serialize};
use serde_json::json;
use regex::Regex;
use shlex;
use rusqlite;
use headless_chrome::{Browser, LaunchOptions, Tab};

use crate::modules::permissions::{Permission, PermissionsGuard};

const DEFAULT_MAX_RUNTIME_SECONDS: u64 = 30;
const DEFAULT_MAX_OUTPUT_BYTES: usize = 512 * 1024;

// ── Policy Types ──────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DirectoryPolicy {
    pub directory: String,
    #[serde(default)]
    pub allowed_commands: Vec<String>,
    #[serde(default)]
    pub allowed_arg_patterns: HashMap<String, Vec<String>>,
    #[serde(default = "default_max_runtime")]
    pub max_runtime_seconds: u64,
    #[serde(default = "default_max_output")]
    pub max_output_bytes: usize,
}

fn default_max_runtime() -> u64 {
    DEFAULT_MAX_RUNTIME_SECONDS
}

fn default_max_output() -> usize {
    DEFAULT_MAX_OUTPUT_BYTES
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct PolicyConfig {
    #[serde(default)]
    pub permanent_blocklist: Vec<String>,
    #[serde(default)]
    pub denylist: Vec<String>,
    #[serde(default)]
    pub directories: Vec<DirectoryPolicy>,
    #[serde(default)]
    pub browser_allowed_origins: Vec<String>,
}

pub struct PolicyEngine {
    workspace_root: PathBuf,
    project_policy_path: PathBuf,
    global_policy_path: PathBuf,
    effective: Arc<Mutex<PolicyConfig>>,
}

impl PolicyEngine {
    pub fn new(workspace_root: PathBuf) -> Self {
        let project_policy_path = workspace_root.join(".vloop").join("policy.json");
        let global_policy_path = dirs::home_dir()
            .unwrap_or_else(|| PathBuf::from("."))
            .join(".vloop")
            .join("policy.json");

        let engine = Self {
            workspace_root,
            project_policy_path,
            global_policy_path,
            effective: Arc::new(Mutex::new(PolicyConfig::default())),
        };
        engine.reload();
        engine
    }

    pub fn reload(&self) {
        let global_cfg = self.load_file(&self.global_policy_path).unwrap_or_default();
        let project_cfg = self.load_file(&self.project_policy_path).unwrap_or_default();

        let builtin_blocklist = vec![
            "mkfs".to_string(),
            "fdisk".to_string(),
            "parted".to_string(),
            "shred".to_string(),
            "wipefs".to_string(),
        ];

        let mut permanent: HashSet<String> = builtin_blocklist.into_iter().collect();
        permanent.extend(global_cfg.permanent_blocklist);
        permanent.extend(project_cfg.permanent_blocklist);

        let mut denylist = if !project_cfg.denylist.is_empty() {
            project_cfg.denylist
        } else {
            global_cfg.denylist
        };
        if denylist.is_empty() {
            denylist = vec![
                "sudo".to_string(),
                "su".to_string(),
                "passwd".to_string(),
                "chown".to_string(),
                "chmod".to_string(),
            ];
        }

        let mut directories = HashMap::new();
        for d in global_cfg.directories {
            directories.insert(d.directory.clone(), d);
        }
        for d in project_cfg.directories {
            directories.insert(d.directory.clone(), d);
        }

        let mut browser_allowed_origins = vec![
            "http://localhost".to_string(),
            "http://127.0.0.1".to_string(),
            "https://localhost".to_string(),
            "https://127.0.0.1".to_string(),
        ];
        browser_allowed_origins.extend(global_cfg.browser_allowed_origins);
        browser_allowed_origins.extend(project_cfg.browser_allowed_origins);

        let mut eff = self.effective.lock().unwrap();
        *eff = PolicyConfig {
            permanent_blocklist: permanent.into_iter().collect(),
            denylist,
            directories: directories.into_values().collect(),
            browser_allowed_origins,
        };
    }

    fn load_file(&self, path: &Path) -> Option<PolicyConfig> {
        if path.exists() {
            if let Ok(content) = std::fs::read_to_string(path) {
                if let Ok(cfg) = serde_json::from_str(&content) {
                    return Some(cfg);
                }
            }
        }
        None
    }

    pub fn save_project_policy(&self, config: PolicyConfig) -> Result<(), String> {
        let parent = self.project_policy_path.parent().unwrap();
        std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;

        let builtin_blocklist = ["mkfs", "fdisk", "parted", "shred", "wipefs"];
        let safe_perm: Vec<String> = config.permanent_blocklist
            .into_iter()
            .filter(|c| !builtin_blocklist.contains(&c.as_str()))
            .collect();

        let val = json!({
            "permanent_blocklist": safe_perm,
            "denylist": config.denylist,
            "directories": config.directories,
            "browser_allowed_origins": config.browser_allowed_origins,
        });

        let file = std::fs::File::create(&self.project_policy_path).map_err(|e| e.to_string())?;
        serde_json::to_writer_pretty(file, &val).map_err(|e| e.to_string())?;
        self.reload();
        Ok(())
    }

    pub fn get_effective(&self) -> PolicyConfig {
        self.effective.lock().unwrap().clone()
    }

    pub fn check_shell_injection(&self, raw_command: &str) -> Result<(), String> {
        static RE: OnceLock<Regex> = OnceLock::new();
        let re = RE.get_or_init(|| {
            Regex::new(
                r"(?x)
                \$\(          |   # $( ... )
                `             |   # backtick subshell
                \$\{[^}]*\}   |   # ${...} variable expansion
                \beval\b      |   # eval
                \|\s*eval\b   |   # pipe to eval
                &&|\|\|       |   # shell boolean chaining
                ;\s*\w        |   # command chaining with ;
                >>\s*\S       |   # append redirect
                >\s*\S        |   # output redirect
                <\s*\(        |   # process substitution
                \|\s*\w           # pipes
                "
            ).unwrap()
        });

        if re.is_match(raw_command) {
            return Err(format!(
                "Command contains disallowed shell characters: {:?}",
                raw_command
            ));
        }
        Ok(())
    }

    pub fn check_command(
        &self,
        binary: &str,
        argv: &[String],
        cwd_abs: &Path,
    ) -> Result<DirectoryPolicy, String> {
        let binary_name = Path::new(binary)
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or(binary);

        let eff = self.get_effective();

        // 1. Permanent blocklist
        for blocked in &eff.permanent_blocklist {
            if command_matches(blocked, binary_name) {
                return Err(format!("Command {:?} is permanently blocked.", binary_name));
            }
        }

        // 2. Denylist
        for denied in &eff.denylist {
            if command_matches(denied, binary_name) {
                return Err(format!("Command {:?} is in the denylist.", binary_name));
            }
        }

        // 3. Allowlist
        let rel_cwd = self.relative_cwd(cwd_abs);
        let mut matched_policy: Option<DirectoryPolicy> = None;

        for dir_policy in &eff.directories {
            let policy_dir = Path::new(&dir_policy.directory);
            if (rel_cwd == policy_dir || (
                policy_dir != Path::new(".") && path_is_under(&rel_cwd, policy_dir)
            ) || (
                policy_dir == Path::new(".") && rel_cwd == Path::new(".")
            ))
                && (matched_policy.is_none() || dir_policy.directory.len() > matched_policy.as_ref().unwrap().directory.len()) {
                    matched_policy = Some(dir_policy.clone());
                }
        }

        let matched = match matched_policy {
            Some(p) => p,
            None => {
                return Err(format!(
                    "No allowlist entry permits {:?} in directory {:?}. Add entry to .vloop/policy.json.",
                    binary_name, rel_cwd
                ));
            }
        };

        if !matched.allowed_commands.iter().any(|c| c == binary_name) {
            return Err(format!(
                "Command {:?} is not in the allowlist for directory {:?}.",
                binary_name, matched.directory
            ));
        }

        // 4. Arguments Check
        if let Some(patterns) = matched.allowed_arg_patterns.get(binary_name) {
            if !patterns.is_empty() {
                let arg_string = argv.join(" ");
                let mut matched_pattern = false;
                for pat in patterns {
                    if let Ok(re) = Regex::new(pat) {
                        if re.is_match(&arg_string) {
                            matched_pattern = true;
                            break;
                        }
                    }
                }
                if !matched_pattern {
                    return Err(format!(
                        "Arguments {:?} for {:?} do not match any allowed pattern: {:?}",
                        argv, binary_name, patterns
                    ));
                }
            }
        }

        Ok(matched)
    }

    fn relative_cwd(&self, cwd_abs: &Path) -> PathBuf {
        let canonical_cwd = cwd_abs.canonicalize().unwrap_or_else(|_| cwd_abs.to_path_buf());
        let canonical_workspace = self.workspace_root.canonicalize().unwrap_or_else(|_| self.workspace_root.clone());
        canonical_cwd.strip_prefix(&canonical_workspace)
            .map(|p| if p.to_string_lossy().is_empty() { PathBuf::from(".") } else { p.to_path_buf() })
            .unwrap_or_else(|_| PathBuf::from("."))
    }
}

fn command_matches(pattern: &str, command: &str) -> bool {
    let p = pattern.split_whitespace().next().unwrap_or("");
    let c = command.split_whitespace().next().unwrap_or("");
    p == c
}

fn path_is_under(path: &Path, parent: &Path) -> bool {
    path.starts_with(parent) && path != parent
}

// ── Confirmation Store ───────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PendingConfirmation {
    pub token: String,
    pub description: String,
    pub risk_level: String,
    pub action_name: String,
    pub action_params: serde_json::Value,
    pub expires_at: u64,
}

pub struct ConfirmationStore {
    pending: Arc<Mutex<HashMap<String, PendingConfirmation>>>,
}

impl ConfirmationStore {
    pub fn new() -> Self {
        Self {
            pending: Arc::new(Mutex::new(HashMap::new())),
        }
    }

    pub fn create(
        &self,
        description: String,
        risk_level: String,
        action_name: String,
        action_params: serde_json::Value,
    ) -> PendingConfirmation {
        let token = uuid::Uuid::new_v4().to_string();
        let expires_at = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_secs() + 60;
        let confirmation = PendingConfirmation {
            token: token.clone(),
            description,
            risk_level,
            action_name,
            action_params,
            expires_at,
        };
        self.pending.lock().unwrap().insert(token, confirmation.clone());
        confirmation
    }

    pub fn get(&self, token: &str) -> Option<PendingConfirmation> {
        let pending = self.pending.lock().unwrap();
        if let Some(conf) = pending.get(token) {
            let now = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_secs();
            if now < conf.expires_at {
                return Some(conf.clone());
            }
        }
        None
    }

    pub fn confirm(&self, token: &str) -> Result<PendingConfirmation, String> {
        let mut pending = self.pending.lock().unwrap();
        if let Some(conf) = pending.remove(token) {
            let now = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_secs();
            if now < conf.expires_at {
                return Ok(conf);
            }
            return Err("Confirmation token expired.".to_string());
        }
        Err("Confirmation token not found.".to_string())
    }

    pub fn cancel(&self, token: &str) {
        self.pending.lock().unwrap().remove(token);
    }

    pub fn list(&self) -> Vec<PendingConfirmation> {
        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_secs();
        let mut pending = self.pending.lock().unwrap();
        pending.retain(|_, v| now < v.expires_at);
        pending.values().cloned().collect()
    }
}

// ── Tool Result ──────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolResult {
    pub success: bool,
    pub output: Option<String>,
    pub error: Option<String>,
    pub exit_code: Option<i32>,
    pub metadata: serde_json::Value,
}

impl ToolResult {
    pub fn success(output: String, metadata: serde_json::Value) -> Self {
        Self {
            success: true,
            output: Some(output),
            error: None,
            exit_code: Some(0),
            metadata,
        }
    }

    pub fn error(error: String) -> Self {
        Self {
            success: false,
            output: None,
            error: Some(error.clone()),
            exit_code: Some(-1),
            metadata: json!({ "error": error }),
        }
    }
}

// ── Global Browser Holder ─────────────────────────────────────────────────────

struct BrowserState {
    browser: Option<Browser>,
}

static BROWSER: OnceLock<Mutex<BrowserState>> = OnceLock::new();

fn get_browser_tab() -> Result<(Browser, Arc<Tab>), String> {
    let mut state = BROWSER.get_or_init(|| Mutex::new(BrowserState { browser: None })).lock().unwrap();
    if state.browser.is_none() {
        let opts = LaunchOptions::default_builder()
            .headless(true)
            .build()
            .map_err(|e| e.to_string())?;
        let browser = Browser::new(opts).map_err(|e| e.to_string())?;
        state.browser = Some(browser);
    }
    let browser = state.browser.as_ref().unwrap().clone();
    let tab = browser.new_tab().map_err(|e| e.to_string())?;
    Ok((browser, tab))
}

fn close_browser() {
    if let Some(lock) = BROWSER.get() {
        let mut state = lock.lock().unwrap();
        state.browser = None;
    }
}

// ── Tools Manager ─────────────────────────────────────────────────────────────

pub struct ToolsManager {
    workspace_root: PathBuf,
    data_dir: PathBuf,
    pub policy: PolicyEngine,
    pub confirmations: ConfirmationStore,
    pub permissions: Arc<Mutex<PermissionsGuard>>,
}

impl ToolsManager {
    pub fn new(workspace_root: PathBuf, data_dir: PathBuf, permissions: Arc<Mutex<PermissionsGuard>>) -> Self {
        let policy = PolicyEngine::new(workspace_root.clone());
        let confirmations = ConfirmationStore::new();
        Self {
            workspace_root,
            data_dir,
            policy,
            confirmations,
            permissions,
        }
    }

    pub async fn execute(
        &self,
        tool_name: &str,
        component_id: Option<&str>,
        session_id: Option<&str>,
        params: serde_json::Value,
    ) -> Result<ToolResult, String> {
        let cid = component_id.unwrap_or("root");

        match tool_name {
            "terminal" => self.execute_terminal(cid, session_id, params).await,
            "filesystem" => self.execute_filesystem(cid, session_id, params).await,
            "browser" => self.execute_browser(cid, session_id, params).await,
            "database" => self.execute_database(cid, session_id, params).await,
            _ => Err(format!("Unknown tool: {:?}", tool_name)),
        }
    }

    fn check_perm(&self, cid: &str, perm: Permission) -> Result<(), String> {
        let guard = self.permissions.lock().unwrap();
        if !guard.has(cid, &perm) {
            return Err(format!("Permission denied: component {:?} lacks {:?}", cid, perm.as_str()));
        }
        Ok(())
    }

    // ── Terminal Tool ─────────────────────────────────────────────────────────

    async fn execute_terminal(
        &self,
        cid: &str,
        _session_id: Option<&str>,
        params: serde_json::Value,
    ) -> Result<ToolResult, String> {
        self.check_perm(cid, Permission::ShellExec)?;
        let operation = params.get("operation").and_then(|v| v.as_str()).unwrap_or("execute");

        if operation == "start_session" {
            let session_id = params.get("session_id").and_then(|v| v.as_str()).ok_or("session_id required")?.to_string();
            let command = params.get("command").and_then(|v| v.as_str()).unwrap_or("bash").to_string();
            let args_val = params.get("args").and_then(|v| v.as_array());
            let mut args = Vec::new();
            if let Some(arr) = args_val {
                for a in arr {
                    if let Some(s) = a.as_str() {
                        args.push(s.to_string());
                    }
                }
            }
            let cwd_relative = params.get("cwd_relative").and_then(|v| v.as_str()).unwrap_or(".");
            let cwd_abs = self.workspace_root.join(cwd_relative);
            let canonical_cwd = cwd_abs.canonicalize().map_err(|e| format!("Invalid working dir: {}", e))?;
            let canonical_workspace = self.workspace_root.canonicalize().unwrap();
            if !canonical_cwd.starts_with(&canonical_workspace) {
                return Ok(ToolResult::error("CWD is outside of the workspace sandbox.".to_string()));
            }

            self.policy.check_command(&command, &args, &canonical_cwd)?;

            let log_dir = self.data_dir.join(".terminal").join(&session_id);

            crate::modules::terminal::start_local_session(
                session_id.clone(),
                canonical_cwd,
                command,
                args,
                log_dir,
            ).await?;

            return Ok(ToolResult::success(format!("Session {} started", session_id), json!({"session_id": session_id})));
        } else if operation == "send_keys" {
            let session_id = params.get("session_id").and_then(|v| v.as_str()).ok_or("session_id required")?;
            let keys = params.get("keys").and_then(|v| v.as_str()).unwrap_or("");
            crate::modules::terminal::send_keys(session_id, keys)?;
            return Ok(ToolResult::success("Keys sent".to_string(), json!({})));
        } else if operation == "read_buffer" {
            let session_id = params.get("session_id").and_then(|v| v.as_str()).ok_or("session_id required")?;
            let buffer = crate::modules::terminal::read_buffer(session_id)?;
            return Ok(ToolResult::success(buffer.clone(), json!({"buffer": buffer})));
        } else if operation == "close_session" {
            let session_id = params.get("session_id").and_then(|v| v.as_str()).ok_or("session_id required")?;
            crate::modules::terminal::close_session(session_id)?;
            return Ok(ToolResult::success("Session closed".to_string(), json!({})));
        }

        let command = params.get("command").and_then(|v| v.as_str()).unwrap_or("");
        let cwd_relative = params.get("cwd_relative").and_then(|v| v.as_str()).unwrap_or(".");
        let timeout_override = params.get("timeout").and_then(|v| v.as_u64());

        if command.trim().is_empty() {
            return Ok(ToolResult::error("No command provided.".to_string()));
        }

        self.policy.check_shell_injection(command)?;

        let argv = shlex::split(command).ok_or("Failed to parse command arguments")?;
        if argv.is_empty() {
            return Ok(ToolResult::error("Empty command after parsing.".to_string()));
        }

        let binary = &argv[0];
        let args = &argv[1..];

        let cwd_abs = self.workspace_root.join(cwd_relative);
        let canonical_cwd = cwd_abs.canonicalize().map_err(|e| format!("Invalid working dir: {}", e))?;
        let canonical_workspace = self.workspace_root.canonicalize().unwrap();
        if !canonical_cwd.starts_with(&canonical_workspace) {
            return Ok(ToolResult::error("CWD is outside of the workspace sandbox.".to_string()));
        }

        let dir_policy = self.policy.check_command(binary, args, &canonical_cwd)?;

        let timeout_secs = timeout_override.unwrap_or(dir_policy.max_runtime_seconds);
        let max_output_bytes = dir_policy.max_output_bytes;

        // Run process
        let mut cmd = tokio::process::Command::new(binary);
        cmd.args(args);
        cmd.current_dir(&canonical_cwd);
        // Stripped env
        cmd.env_clear();
        for key in &["PATH", "HOME", "LANG", "TERM", "USER", "LOGNAME"] {
            if let Ok(val) = std::env::var(key) {
                cmd.env(key, val);
            }
        }
        cmd.stdout(std::process::Stdio::piped());
        cmd.stderr(std::process::Stdio::piped());

        let mut child = cmd.spawn().map_err(|e| format!("Spawn error: {}", e))?;

        let timeout_fut = tokio::time::sleep(Duration::from_secs(timeout_secs));
        tokio::pin!(timeout_fut);

        tokio::select! {
            res = child.wait() => {
                let status = res.map_err(|e| e.to_string())?;
                let output = child.wait_with_output().await.map_err(|e| e.to_string())?;

                let stdout_len = output.stdout.len();
                let stderr_len = output.stderr.len();

                let mut out_str = String::from_utf8_lossy(&output.stdout[..stdout_len.min(max_output_bytes)]).into_owned();
                let err_str = String::from_utf8_lossy(&output.stderr[..stderr_len.min(max_output_bytes)]).into_owned();

                if !err_str.is_empty() {
                    out_str = format!("{}\n[stderr]\n{}", out_str, err_str);
                }

                let exit_code = status.code().unwrap_or(-1);
                Ok(ToolResult {
                    success: status.success(),
                    output: Some(out_str),
                    error: if status.success() { None } else { Some(format!("Process exited with code {}", exit_code)) },
                    exit_code: Some(exit_code),
                    metadata: json!({
                        "command": command,
                        "cwd": canonical_cwd.to_string_lossy(),
                        "exit_code": exit_code,
                        "truncated": stdout_len > max_output_bytes || stderr_len > max_output_bytes,
                    })
                })
            }
            _ = &mut timeout_fut => {
                let _ = child.kill().await;
                Ok(ToolResult::error(format!("Command timed out after {}s.", timeout_secs)))
            }
        }
    }

    // ── Filesystem Tool ───────────────────────────────────────────────────────

    async fn execute_filesystem(
        &self,
        cid: &str,
        _session_id: Option<&str>,
        params: serde_json::Value,
    ) -> Result<ToolResult, String> {
        self.check_perm(cid, Permission::FilesystemRead)?;

        let operation = params.get("operation").and_then(|v| v.as_str()).unwrap_or("");
        match operation {
            "list" => {
                let rel_path = params.get("path").and_then(|v| v.as_str()).unwrap_or(".");
                let abs_path = self.resolve_path(rel_path)?;
                if !abs_path.exists() {
                    return Ok(ToolResult::error(format!("Path does not exist: {:?}", rel_path)));
                }
                if !abs_path.is_dir() {
                    return Ok(ToolResult::error(format!("Not a directory: {:?}", rel_path)));
                }
                let mut entries = Vec::new();
                if let Ok(read_dir) = std::fs::read_dir(&abs_path) {
                    for entry in read_dir.flatten() {
                        let metadata = entry.metadata().ok();
                        entries.push(json!({
                            "name": entry.file_name().to_string_lossy(),
                            "type": if entry.path().is_dir() { "dir" } else { "file" },
                            "size": metadata.as_ref().map(|m| m.len()),
                            "mtime": metadata.as_ref().and_then(|m| m.modified().ok().and_then(|t| t.duration_since(UNIX_EPOCH).ok().map(|d| d.as_secs_f64()))),
                        }));
                    }
                }
                Ok(ToolResult::success("".to_string(), json!({
                    "path": abs_path.to_string_lossy(),
                    "entries": entries,
                })))
            }
            "read" => {
                let rel_path = params.get("path").and_then(|v| v.as_str()).unwrap_or("");
                let abs_path = self.resolve_path(rel_path)?;
                if !abs_path.exists() {
                    return Ok(ToolResult::error(format!("File not found: {:?}", rel_path)));
                }
                if abs_path.is_dir() {
                    return Ok(ToolResult::error(format!("Path is a directory: {:?}", rel_path)));
                }
                let data = std::fs::read(&abs_path).map_err(|e| format!("Read error: {}", e))?;
                let is_binary = data.iter().take(1024).any(|&b| b == 0);
                if is_binary {
                    use base64::{Engine as _, engine::general_purpose};
                    let limit = data.len().min(1024 * 1024);
                    let b64 = general_purpose::STANDARD.encode(&data[..limit]);
                    Ok(ToolResult::success(b64, json!({
                        "path": abs_path.to_string_lossy(),
                        "encoding": "base64",
                        "size": data.len(),
                        "truncated": data.len() > 1024 * 1024,
                    })))
                } else {
                    let limit = data.len().min(1024 * 1024);
                    let text = String::from_utf8_lossy(&data[..limit]).into_owned();
                    Ok(ToolResult::success(text, json!({
                        "path": abs_path.to_string_lossy(),
                        "encoding": "utf-8",
                        "size": data.len(),
                        "truncated": data.len() > 1024 * 1024,
                    })))
                }
            }
            "stat" => {
                let rel_path = params.get("path").and_then(|v| v.as_str()).unwrap_or("");
                let abs_path = self.resolve_path(rel_path)?;
                if !abs_path.exists() {
                    return Ok(ToolResult::error(format!("Path not found: {:?}", rel_path)));
                }
                let metadata = abs_path.metadata().map_err(|e| format!("Stat error: {}", e))?;
                Ok(ToolResult::success("".to_string(), json!({
                    "path": abs_path.to_string_lossy(),
                    "type": if abs_path.is_dir() { "dir" } else { "file" },
                    "size": metadata.len(),
                    "mtime": metadata.modified().ok().and_then(|t| t.duration_since(UNIX_EPOCH).ok().map(|d| d.as_secs_f64())),
                })))
            }
            "write" => {
                self.check_perm(cid, Permission::FilesystemWrite)?;
                let rel_path = params.get("path").and_then(|v| v.as_str()).unwrap_or("");
                let content = params.get("content").and_then(|v| v.as_str()).unwrap_or("");
                let create_parents = params.get("create_parents").and_then(|v| v.as_bool()).unwrap_or(false);
                let confirmation_token = params.get("_confirmation_token").and_then(|v| v.as_str());

                let abs_path = self.resolve_path(rel_path)?;
                if abs_path.exists() && abs_path.is_file() && confirmation_token.is_none() {
                    let pending = self.confirmations.create(
                        format!("Overwrite existing file: {}", rel_path),
                        "caution".to_string(),
                        "write".to_string(),
                        params,
                    );
                    return Err(format!("ConfirmationRequired: {}", pending.token));
                }

                if let Some(token) = confirmation_token {
                    self.confirmations.confirm(token)?;
                }

                if create_parents {
                    if let Some(parent) = abs_path.parent() {
                        std::fs::create_dir_all(parent).map_err(|e| format!("Parent directory creation failed: {}", e))?;
                    }
                }

                std::fs::write(&abs_path, content).map_err(|e| format!("Write failed: {}", e))?;
                Ok(ToolResult::success("".to_string(), json!({
                    "path": abs_path.to_string_lossy(),
                    "bytes_written": content.len(),
                })))
            }
            "create" => {
                self.check_perm(cid, Permission::FilesystemWrite)?;
                let rel_path = params.get("path").and_then(|v| v.as_str()).unwrap_or("");
                let is_dir = params.get("is_dir").and_then(|v| v.as_bool()).unwrap_or(false);

                let abs_path = self.resolve_path(rel_path)?;
                if abs_path.exists() {
                    return Ok(ToolResult::error(format!("Path already exists: {:?}", rel_path)));
                }

                if is_dir {
                    std::fs::create_dir_all(&abs_path).map_err(|e| format!("Create directory failed: {}", e))?;
                } else {
                    if let Some(parent) = abs_path.parent() {
                        std::fs::create_dir_all(parent).ok();
                    }
                    std::fs::File::create(&abs_path).map_err(|e| format!("Create file failed: {}", e))?;
                }
                Ok(ToolResult::success("".to_string(), json!({
                    "path": abs_path.to_string_lossy(),
                    "type": if is_dir { "dir" } else { "file" },
                })))
            }
            "delete" => {
                self.check_perm(cid, Permission::FilesystemWrite)?;
                let rel_path = params.get("path").and_then(|v| v.as_str()).unwrap_or("");
                let recursive = params.get("recursive").and_then(|v| v.as_bool()).unwrap_or(false);
                let confirmation_token = params.get("_confirmation_token").and_then(|v| v.as_str());

                let abs_path = self.resolve_path(rel_path)?;
                if !abs_path.exists() {
                    return Ok(ToolResult::error(format!("Path not found: {:?}", rel_path)));
                }

                if confirmation_token.is_none() {
                    let kind = if abs_path.is_dir() { "directory tree" } else { "file" };
                    let pending = self.confirmations.create(
                        format!("Permanently delete {}: {}", kind, rel_path),
                        "destructive".to_string(),
                        "delete".to_string(),
                        params,
                    );
                    return Err(format!("ConfirmationRequired: {}", pending.token));
                }

                if let Some(token) = confirmation_token {
                    self.confirmations.confirm(token)?;
                }

                if abs_path.is_dir() {
                    if recursive {
                        std::fs::remove_dir_all(&abs_path).map_err(|e| format!("Delete dir failed: {}", e))?;
                    } else {
                        std::fs::remove_dir(&abs_path).map_err(|e| format!("Delete dir failed: {}", e))?;
                    }
                } else {
                    std::fs::remove_file(&abs_path).map_err(|e| format!("Delete file failed: {}", e))?;
                }
                Ok(ToolResult::success("".to_string(), json!({
                    "path": abs_path.to_string_lossy(),
                    "recursive": recursive,
                })))
            }
            "move" => {
                self.check_perm(cid, Permission::FilesystemWrite)?;
                let src_rel = params.get("src").and_then(|v| v.as_str()).unwrap_or("");
                let dest_rel = params.get("dest").and_then(|v| v.as_str()).unwrap_or("");
                let confirmation_token = params.get("_confirmation_token").and_then(|v| v.as_str());

                let src_abs = self.resolve_path(src_rel)?;
                let dest_abs = self.resolve_path(dest_rel)?;

                if !src_abs.exists() {
                    return Ok(ToolResult::error(format!("Source not found: {:?}", src_rel)));
                }

                if confirmation_token.is_none() {
                    let pending = self.confirmations.create(
                        format!("Move {:?} -> {:?}", src_rel, dest_rel),
                        "destructive".to_string(),
                        "move".to_string(),
                        params,
                    );
                    return Err(format!("ConfirmationRequired: {}", pending.token));
                }

                if let Some(token) = confirmation_token {
                    self.confirmations.confirm(token)?;
                }

                std::fs::rename(&src_abs, &dest_abs).map_err(|e| format!("Move failed: {}", e))?;
                Ok(ToolResult::success("".to_string(), json!({
                    "src": src_abs.to_string_lossy(),
                    "dest": dest_abs.to_string_lossy(),
                })))
            }
            _ => Err(format!("Unknown filesystem operation: {:?}", operation)),
        }
    }

    fn resolve_path(&self, rel: &str) -> Result<PathBuf, String> {
        let abs = self.workspace_root.join(rel);
        let canonical_abs = abs.canonicalize().unwrap_or_else(|_| abs.clone());
        let canonical_workspace = self.workspace_root.canonicalize().unwrap_or_else(|_| self.workspace_root.clone());
        if !canonical_abs.starts_with(&canonical_workspace) {
            return Err(format!("Path {:?} is outside of the workspace sandbox", rel));
        }
        Ok(canonical_abs)
    }

    // ── Browser Tool ──────────────────────────────────────────────────────────

    async fn execute_browser(
        &self,
        cid: &str,
        _session_id: Option<&str>,
        params: serde_json::Value,
    ) -> Result<ToolResult, String> {
        self.check_perm(cid, Permission::NetworkOutbound)?;

        let operation = params.get("operation").and_then(|v| v.as_str()).unwrap_or("");
        if operation == "close" {
            close_browser();
            return Ok(ToolResult::success("Browser closed.".to_string(), json!({})));
        }

        let (_browser, tab) = get_browser_tab()?;

        match operation {
            "navigate" => {
                let url = params.get("url").and_then(|v| v.as_str()).ok_or("Url param required")?;
                self.check_browser_url(url)?;

                tab.navigate_to(url).map_err(|e| e.to_string())?;
                tab.wait_until_navigated().map_err(|e| e.to_string())?;

                let title = tab.get_title().unwrap_or_default();
                let current_url = tab.get_url();

                Ok(ToolResult::success(
                    format!("Navigated to {:?} - title: {:?}", current_url, title),
                    json!({ "title": title, "url": current_url }),
                ))
            }
            "screenshot" => {
                use base64::{Engine as _, engine::general_purpose};
                let png = tab.capture_screenshot(
                    headless_chrome::protocol::cdp::Page::CaptureScreenshotFormatOption::Png,
                    None,
                    None,
                    true
                ).map_err(|e| e.to_string())?;

                let b64 = general_purpose::STANDARD.encode(&png);
                Ok(ToolResult::success(b64, json!({ "format": "png" })))
            }
            "get_text" => {
                let html = tab.get_content().map_err(|e| e.to_string())?;
                // Minimal text extraction by stripping tags (simple HTML strip)
                let text: String = html.chars().fold((String::new(), false), |(mut s, mut in_tag), c| {
                    if c == '<' {
                        in_tag = true;
                    } else if c == '>' {
                        in_tag = false;
                    } else if !in_tag {
                        s.push(c);
                    }
                    (s, in_tag)
                }).0;
                let limit = text.len().min(DEFAULT_MAX_OUTPUT_BYTES);
                Ok(ToolResult::success(text[..limit].to_string(), json!({})))
            }
            "get_html" => {
                let html = tab.get_content().map_err(|e| e.to_string())?;
                let limit = html.len().min(DEFAULT_MAX_OUTPUT_BYTES);
                Ok(ToolResult::success(html[..limit].to_string(), json!({})))
            }
            "click" => {
                let selector = params.get("selector").and_then(|v| v.as_str()).ok_or("Selector required")?;
                let elem = tab.wait_for_element(selector).map_err(|e| e.to_string())?;
                elem.click().map_err(|e| e.to_string())?;
                Ok(ToolResult::success(format!("Clicked element {:?}", selector), json!({})))
            }
            "fill" => {
                let selector = params.get("selector").and_then(|v| v.as_str()).ok_or("Selector required")?;
                let value = params.get("value").and_then(|v| v.as_str()).ok_or("Value required")?;
                let elem = tab.wait_for_element(selector).map_err(|e| e.to_string())?;
                elem.type_into(value).map_err(|e| e.to_string())?;
                Ok(ToolResult::success(format!("Filled element {:?} with {:?}", selector, value), json!({})))
            }
            "eval_js" => {
                self.check_perm(cid, Permission::ShellExec)?;
                let expression = params.get("expression").and_then(|v| v.as_str()).ok_or("Expression required")?;
                let val = tab.evaluate(expression, true).map_err(|e| e.to_string())?;
                Ok(ToolResult::success(
                    format!("{:?}", val.value),
                    json!({ "value": val.value }),
                ))
            }
            _ => Err(format!("Unknown browser operation: {:?}", operation)),
        }
    }

    fn check_browser_url(&self, url: &str) -> Result<(), String> {
        let eff = self.policy.get_effective();
        if !eff.browser_allowed_origins.iter().any(|prefix| url.starts_with(prefix)) {
            return Err(format!(
                "URL {:?} is not in browser allowed origins. Configure browser_allowed_origins in policy.json.",
                url
            ));
        }
        Ok(())
    }

    // ── Database Tool ─────────────────────────────────────────────────────────

    async fn execute_database(
        &self,
        cid: &str,
        _session_id: Option<&str>,
        params: serde_json::Value,
    ) -> Result<ToolResult, String> {
        self.check_perm(cid, Permission::FilesystemRead)?;

        let operation = params.get("operation").and_then(|v| v.as_str()).unwrap_or("");
        let state_db_path = self.data_dir.join("state.db");

        match operation {
            "schema_info" => {
                let conn = rusqlite::Connection::open(&state_db_path).map_err(|e| format!("DB Open failed: {}", e))?;
                let mut stmt = conn.prepare("SELECT name FROM sqlite_master WHERE type='table'").map_err(|e| e.to_string())?;
                let tables_iter = stmt.query_map([], |row| row.get::<_, String>(0)).map_err(|e| e.to_string())?;

                let mut schema: HashMap<String, serde_json::Value> = HashMap::new();
                for tbl in tables_iter.flatten() {
                    let mut col_stmt = conn.prepare(&format!("PRAGMA table_info({})", tbl)).map_err(|e| e.to_string())?;
                    let cols_iter = col_stmt.query_map([], |row| {
                        Ok(json!({
                            "name": row.get::<_, String>(1)?,
                            "type": row.get::<_, String>(2)?,
                            "nullable": row.get::<usize, i32>(3)? == 0,
                        }))
                    }).map_err(|e| e.to_string())?;

                    let mut columns = Vec::new();
                    for c in cols_iter.flatten() {
                        columns.push(c);
                    }
                    schema.insert(tbl, json!({ "columns": columns }));
                }

                Ok(ToolResult::success(
                    serde_json::to_string_pretty(&schema).unwrap(),
                    json!({ "table_count": schema.len() }),
                ))
            }
            "query_read" => {
                let sql = params.get("sql").and_then(|v| v.as_str()).unwrap_or("");
                let _bind_params = params.get("params").unwrap_or(&json!({}));

                if sql.trim().is_empty() {
                    return Ok(ToolResult::error("'sql' parameter is required".to_string()));
                }

                let drop_alter_re = Regex::new(r"(?i)\b(DROP\s+TABLE|DROP\s+DATABASE|TRUNCATE|ALTER\s+TABLE)\b").unwrap();
                if drop_alter_re.is_match(sql) {
                    return Ok(ToolResult::error("Query contains a permanently blocked statement (DROP/TRUNCATE/ALTER).".to_string()));
                }

                let select_re = Regex::new(r"(?i)^\s*SELECT\b").unwrap();
                if !select_re.is_match(sql) {
                    return Ok(ToolResult::error("query_read only accepts SELECT statements. Use query_write for mutations.".to_string()));
                }

                let conn = rusqlite::Connection::open(&state_db_path).map_err(|e| format!("DB Open failed: {}", e))?;
                let mut stmt = conn.prepare(sql).map_err(|e| e.to_string())?;

                let col_names: Vec<String> = stmt.column_names().into_iter().map(|s| s.to_string()).collect();
                let col_count = stmt.column_count();

                let mut rows_out = Vec::new();
                let mut rows_iter = stmt.query([]).map_err(|e| e.to_string())?; // Simple query without named bindings for rust bridge, or map parameters
                while let Some(row) = rows_iter.next().map_err(|e| e.to_string())? {
                    let mut r_map = serde_json::Map::new();
                    #[allow(clippy::needless_range_loop)]
                    for idx in 0..col_count {
                        let name = &col_names[idx];
                        let val: rusqlite::types::Value = row.get(idx).unwrap_or(rusqlite::types::Value::Null);
                        let json_val = match val {
                            rusqlite::types::Value::Null => serde_json::Value::Null,
                            rusqlite::types::Value::Integer(i) => json!(i),
                            rusqlite::types::Value::Real(f) => json!(f),
                            rusqlite::types::Value::Text(t) => json!(t),
                            rusqlite::types::Value::Blob(b) => json!(b),
                        };
                        r_map.insert(name.clone(), json_val);
                    }
                    rows_out.push(serde_json::Value::Object(r_map));
                    if rows_out.len() >= 500 {
                        break;
                    }
                }

                Ok(ToolResult::success(
                    serde_json::to_string_pretty(&rows_out).unwrap(),
                    json!({ "row_count": rows_out.len() }),
                ))
            }
            "query_write" => {
                self.check_perm(cid, Permission::FilesystemWrite)?;
                let sql = params.get("sql").and_then(|v| v.as_str()).unwrap_or("");
                let confirmation_token = params.get("_confirmation_token").and_then(|v| v.as_str());

                if sql.trim().is_empty() {
                    return Ok(ToolResult::error("'sql' parameter is required".to_string()));
                }

                let drop_alter_re = Regex::new(r"(?i)\b(DROP\s+TABLE|DROP\s+DATABASE|TRUNCATE|ALTER\s+TABLE)\b").unwrap();
                if drop_alter_re.is_match(sql) {
                    return Ok(ToolResult::error("Query contains a permanently blocked statement (DROP/TRUNCATE/ALTER).".to_string()));
                }

                let write_re = Regex::new(r"(?i)^\s*(INSERT|UPDATE|DELETE)\b").unwrap();
                if !write_re.is_match(sql) {
                    return Ok(ToolResult::error("query_write only accepts INSERT/UPDATE/DELETE statements.".to_string()));
                }

                if confirmation_token.is_none() {
                    let pending = self.confirmations.create(
                        format!("Execute write query: {}", if sql.len() > 120 { &sql[..120] } else { sql }),
                        "destructive".to_string(),
                        "query_write".to_string(),
                        params,
                    );
                    return Err(format!("ConfirmationRequired: {}", pending.token));
                }

                if let Some(token) = confirmation_token {
                    self.confirmations.confirm(token)?;
                }

                let conn = rusqlite::Connection::open(&state_db_path).map_err(|e| format!("DB Open failed: {}", e))?;
                let rowcount = conn.execute(sql, []).map_err(|e| e.to_string())?;

                Ok(ToolResult::success(
                    format!("Write query executed successfully. Rows affected: {}", rowcount),
                    json!({ "rowcount": rowcount }),
                ))
            }
            _ => Err(format!("Unknown database operation: {:?}", operation)),
        }
    }
}
