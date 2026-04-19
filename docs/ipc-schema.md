# IPC Schema

## Tauri Commands (harness-ui → harness-core)

### Database

| Command | Input | Output |
|---------|-------|--------|
| `db_query` | `{ sql: string, params: any[] }` | `any[][]` |
| `db_get_agent_runs` | `{ limit: number, offset: number }` | `AgentRun[]` |
| `db_get_logs` | `{ run_id: string, limit: number }` | `LogEntry[]` |
| `db_list_tables` | — | `string[]` |
| `db_config_get` | `{ key: string }` | `string \| null` |
| `db_config_set` | `{ key: string, value: string }` | — |

### Terminal

| Command | Input | Output |
|---------|-------|--------|
| `terminal_create` | `{ shell?: string, cwd?: string }` | `string` (session_id) |
| `terminal_write` | `{ session_id: string, data: string }` | — |
| `terminal_resize` | `{ session_id: string, cols: number, rows: number }` | — |
| `terminal_kill` | `{ session_id: string }` | — |
| `terminal_list` | — | `TerminalSessionInfo[]` |

### File System

All FS commands resolve paths against the configured VFS root (`VLOOP_VFS_ROOT`, defaulting to
`$HOME`).  Any path that would escape the root is rejected with an error — the caller never needs
to sanitise paths client-side.

| Command | Input | Output |
|---------|-------|--------|
| `fs_list` | `{ path: string }` | `FileEntry[]` |
| `fs_read` | `{ path: string }` | `string` |
| `fs_write` | `{ path: string, content: string }` | — |
| `fs_delete` | `{ path: string }` | — |
| `fs_watch` | `{ path: string }` | `string` (watcher_id) |
| `fs_unwatch` | `{ watcher_id: string }` | — |
| `fs_git_status` | `{ path: string }` | `GitStatus` |
| `fs_git_diff` | `{ path: string }` | `string` (unified patch) |
| `fs_git_commit` | `{ path: string, message: string }` | `string` (commit sha) |
| `fs_git_branches` | `{ path: string }` | `GitBranch[]` |

### Process Manager

| Command | Input | Output |
|---------|-------|--------|
| `process_start` | `ProcessManifest` | `string` (process_id) |
| `process_stop` | `{ id: string }` | — |
| `process_restart` | `{ id: string }` | — |
| `process_list` | — | `ProcessInfo[]` |
| `process_logs` | `{ id: string, limit?: number }` | `ProcessLog[]` |

### Gateway

| Command | Input | Output |
|---------|-------|--------|
| `gateway_list_adapters` | — | `AdapterInfo[]` |
| `gateway_add_adapter` | `AdapterConfig` | `string` (adapter_id) |
| `gateway_remove_adapter` | `{ id: string }` | — |
| `gateway_send` | `{ adapter_id: string, message: string }` | — |

### Host Service

| Command | Input | Output |
|---------|-------|--------|
| `host_start` | `{ port?: number }` | `HostStatus` |
| `host_stop` | — | — |
| `host_status` | — | `HostStatus` |
| `host_rotate_token` | — | `string` (new token) |

## Tauri Events (harness-core → harness-ui)

| Event | Payload |
|-------|---------|
| `terminal_output` | `{ session_id: string, data: string }` |
| `fs_changed` | `{ watcher_id: string, path: string, kind: string }` |
| `process_status_changed` | `{ id: string, status: string, exit_code?: number }` |
| `process_log` | `{ id: string, stream: "stdout"\|"stderr", line: string, ts: string }` |
| `gateway_message` | `{ adapter_id: string, message: string }` |

## Type Definitions

```typescript
interface ProcessManifest {
  name: string;
  command: string;
  args?: string[];
  cwd?: string;
  env?: Record<string, string>;
  port?: number;
  auto_restart?: boolean;
}

interface FileEntry {
  name: string;
  path: string;
  is_dir: boolean;
  size?: number;
  modified?: string;
  git_status?: string;
}

interface HostStatus {
  running: boolean;
  address?: string;
  url?: string;
  qr_png_base64?: string;
  token?: string;
}
```
