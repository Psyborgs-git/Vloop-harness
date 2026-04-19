# Vloop Harness

[![CI](https://github.com/Psyborgs-git/Vloop-harness/actions/workflows/ci.yml/badge.svg)](https://github.com/Psyborgs-git/Vloop-harness/actions/workflows/ci.yml)

**Vloop Harness** is a local-first AI agent workbench built as a Tauri + FastAPI + React monorepo.

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                   harness-ui (React/MUI)              │
│  AgentConsole │ Terminal │ FileExplorer │ Pipeline…  │
└───────────────────────┬──────────────────────────────┘
                        │ Tauri IPC + HTTP
┌───────────────────────▼──────────────────────────────┐
│              harness-core (Rust / Tauri 2)            │
│  DB  │ Terminal  │ FS+Git │ Process │ Gateway │ Host  │
│  :47200 internal REST  │  :47299 LAN host (Axum)      │
└───────────────────────┬──────────────────────────────┘
                        │ HTTP :47201
┌───────────────────────▼──────────────────────────────┐
│           inference-backend (Python / FastAPI)        │
│  DSPy   │  5 Agent Loops  │ Self-Modify │ Tools       │
└──────────────────────────────────────────────────────┘
```

### Port Assignments
| Port  | Service |
|-------|---------|
| 5173  | harness-ui dev server (Vite) |
| 47200 | harness-core internal REST |
| 47201 | inference-backend REST + WebSocket |
| 47299 | LAN host service (QR access) |

## Quick Start

### Prerequisites
- Rust ≥ 1.77, Node ≥ 20, Python ≥ 3.11
- [Ollama](https://ollama.ai) (default LLM provider)

```bash
chmod +x scripts/setup.sh && ./scripts/setup.sh
./scripts/dev.sh
```

## Features

- **5 Agent Loops**: ReAct, ChainOfThought, PlanAndExecute, ToolCall, MultiAgent
- **Self-Modification**: Agents write Python modules; AST-validated, git-tracked, hot-reloaded
- **Terminal Harness**: Multi-tab xterm.js backed by portable-pty
- **File Explorer**: Monaco editor + git diff viewer with VFS sandbox
- **Pipeline Studio**: ReactFlow drag-and-drop DSPy pipeline editor
- **Adapter Gateway**: stdio / HTTP / WebSocket / Unix socket
- **LAN QR Access**: HMAC-signed one-time token
- **Immutable Telemetry**: SQLite triggers block audit log modification
- **MUI Theming**: Dark/light presets with live customisation

## Structure

```
Vloop-harness/
├── harness-core/      # Rust / Tauri 2 engine
├── inference-backend/ # Python FastAPI + DSPy
├── harness-ui/        # React + Vite + TypeScript
├── scripts/           # Bootstrap & dev scripts
└── docs/              # Architecture & API docs
```

