# Architecture

## Overview

Vloop Harness is a three-tier local-first AI agent workbench:

```
┌──────────────────────────────────────────┐
│  harness-ui  (React 18 + Vite + MUI 5)   │
│                                          │
│  AgentConsole │ Terminal │ FileExplorer  │
│  PipelineStudio │ ProcessManager         │
│  DatabaseExplorer │ GatewayConfig        │
│  HostService │ Settings                  │
└───────────────────┬──────────────────────┘
                    │ Tauri IPC (invoke/listen)
                    │ HTTP → :47201
┌───────────────────▼──────────────────────┐
│  harness-core  (Rust 1.77 / Tauri 2)     │
│                                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │  DB/SQLx │ │ Terminal │ │ FS + Git │ │
│  └──────────┘ └──────────┘ └──────────┘ │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │ Process  │ │ Gateway  │ │   Host   │ │
│  │ Manager  │ │ Adapters │ │  :47299  │ │
│  └──────────┘ └──────────┘ └──────────┘ │
│                                          │
│  Internal REST :47200  │  Telemetry      │
└───────────────────┬──────────────────────┘
                    │ HTTP :47200 (internal)
┌───────────────────▼──────────────────────┐
│  inference-backend (Python 3.11 / FastAPI)│
│                                          │
│  DSPy Core   │  Agent Loops (5)          │
│  Self-Modify │  Tools Registry           │
│  WebSocket /stream                       │
│  REST :47201                             │
└──────────────────────────────────────────┘
```

## Port Assignments

| Port  | Bind      | Purpose |
|-------|-----------|---------|
| 5173  | localhost | Vite dev server (harness-ui) |
| 47200 | localhost | harness-core internal REST (Rust ↔ Python) |
| 47201 | localhost | inference-backend REST + WebSocket |
| 47299 | 0.0.0.0   | LAN host service (QR token entry point) |

## Data Flow

### Agent Run
```
User → InputPanel.tsx
  → POST /agent/run :47201
    → inference-backend agent loop
      → DSPy Predict (Ollama/OpenAI/Anthropic)
      → tool calls via tools/registry
        → shell_exec / file_rw / db_query → :47200
    → WebSocket /stream → StreamMessage frames
  → AgentConsole TaskTrace renders steps live
  → agent_runs / agent_steps written to SQLite
```

### Terminal Session
```
User opens TerminalPanel
  → terminal_create IPC command
    → harness-core spawns portable-pty session
    → async read loop emits terminal_output events
  → XtermInstance.tsx writes to xterm
User types
  → terminal_write IPC
    → PTY master.write()
```

### Self-Modification
```
Agent generates Python code
  → POST /module/create { name, code }
    → writer.py: atomic write to modules/<name>.py
    → validator.py: ast.parse + subprocess import
    → rollback.py: git commit [agent] create module <name>
    → watcher.py hot-reload triggers registry refresh
  → Module available for next agent invocation
```

## Security Model

- **localhost-only**: harness-core and inference-backend bind to 127.0.0.1 only
- **LAN host**: :47299 binds 0.0.0.0 but requires HMAC-signed one-time token
- **VFS sandbox**: all fs_read/fs_write paths canonicalised and checked against project root
- **Immutable telemetry**: SQLite BEFORE DELETE/UPDATE triggers call RAISE(ABORT)
- **Agent code safety**: AST parse + subprocess dry-run import before execution

## Database

SQLite with WAL mode + `PRAGMA synchronous=NORMAL`. Full schema in [db-schema.md](db-schema.md).

Optional Postgres path: set `DB_ENGINE=postgres` in inference-backend `.env`.
