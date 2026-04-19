import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";

// DB
export const dbQuery = (sql: string, params: unknown[] = []) =>
  invoke<unknown[][]>("db_query", { sql, params });

export const dbGetAgentRuns = (limit = 50, offset = 0) =>
  invoke<unknown[]>("db_get_agent_runs", { limit, offset });

export const dbGetLogs = (runId: string, limit = 200) =>
  invoke<unknown[]>("db_get_logs", { run_id: runId, limit });

export const dbListTables = () => invoke<string[]>("db_list_tables");

export const dbConfigGet = (key: string) =>
  invoke<string | null>("db_config_get", { key });

export const dbConfigSet = (key: string, value: string) =>
  invoke<void>("db_config_set", { key, value });

// Terminal
export const terminalCreate = (shell?: string, cwd?: string) =>
  invoke<string>("terminal_create", { shell, cwd });

export const terminalWrite = (sessionId: string, data: string) =>
  invoke<void>("terminal_write", { session_id: sessionId, data });

export const terminalResize = (sessionId: string, cols: number, rows: number) =>
  invoke<void>("terminal_resize", { session_id: sessionId, cols, rows });

export const terminalKill = (sessionId: string) =>
  invoke<void>("terminal_kill", { session_id: sessionId });

export const terminalList = () => invoke<unknown[]>("terminal_list");

// FS
export const fsList = (path: string) => invoke<unknown[]>("fs_list", { path });
export const fsRead = (path: string) => invoke<string>("fs_read", { path });
export const fsWrite = (path: string, content: string) =>
  invoke<void>("fs_write", { path, content });
export const fsDelete = (path: string) => invoke<void>("fs_delete", { path });
export const fsGitStatus = (path: string) =>
  invoke<unknown>("fs_git_status", { path });
export const fsGitDiff = (path: string) =>
  invoke<string>("fs_git_diff", { path });
export const fsGitCommit = (path: string, message: string, paths: string[]) =>
  invoke<string>("fs_git_commit", { path, message, paths });
export const fsGitBranches = (path: string) =>
  invoke<unknown[]>("fs_git_branches", { path });

export const fsWatch = (path: string) =>
  invoke<string>("fs_watch", { path });

export const fsUnwatch = (watcherId: string) =>
  invoke<void>("fs_unwatch", { watcher_id: watcherId });

// Process
export const processStart = (manifest: unknown) =>
  invoke<string>("process_start", { manifest });
export const processStop = (id: string) =>
  invoke<void>("process_stop", { id });
export const processRestart = (id: string) =>
  invoke<void>("process_restart", { id });
export const processList = () => invoke<unknown[]>("process_list");
export const processLogs = (id: string, limit = 200) =>
  invoke<unknown[]>("process_logs", { id, limit });

// Gateway
export const gatewayListAdapters = () =>
  invoke<unknown[]>("gateway_list_adapters");
export const gatewayAddAdapter = (config: unknown) =>
  invoke<string>("gateway_add_adapter", { config });
export const gatewayRemoveAdapter = (id: string) =>
  invoke<void>("gateway_remove_adapter", { id });
export const gatewaySend = (adapterId: string, message: string) =>
  invoke<void>("gateway_send", { adapter_id: adapterId, message });

// Host
export const hostStart = () => invoke<unknown>("host_start");
export const hostStop = () => invoke<void>("host_stop");
export const hostStatus = () => invoke<unknown>("host_status");
export const hostRotateToken = () => invoke<string>("host_rotate_token");

// Events
export const onTerminalOutput = (
  cb: (payload: { session_id: string; data: string }) => void
) => listen<{ session_id: string; data: string }>("terminal_output", (e) => cb(e.payload));

export const onFsChanged = (
  cb: (payload: { watcher_id: string; path: string; kind: string }) => void
) => listen<{ watcher_id: string; path: string; kind: string }>("fs_changed", (e) => cb(e.payload));

export const onProcessLog = (
  cb: (payload: { id: string; stream: string; line: string; ts: string }) => void
) =>
  listen<{ id: string; stream: string; line: string; ts: string }>(
    "process_log",
    (e) => cb(e.payload)
  );
