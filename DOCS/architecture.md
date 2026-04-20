# Architecture

## Overview

Vloop Harness is a native binary application (packaged via PyInstaller) where:

- **Python** is the brain — it owns all state, business logic, event routing, and AI inference.
- **React** is the face — it renders UI and emits user interactions back to Python.

The two halves communicate through a FastAPI server:

```
React App  ←─── WebSocket ──→  Python Component
               (bidirectional)
React App  ←─── REST API   ──→  FastAPI Server  ──→  MainProcess
```

---

## Layer diagram

```
┌──────────────────────────────────────────────────────┐
│  NATIVE WINDOW  (PyWebView)                          │
│  ┌────────────────────────────────────────────────┐  │
│  │  Root UI  /ui/root  (React window manager)     │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐     │  │
│  │  │ View A   │  │ View B   │  │ View C   │ ... │  │
│  │  │ <iframe> │  │ <iframe> │  │ <iframe> │     │  │
│  │  └──────────┘  └──────────┘  └──────────┘     │  │
│  └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
         ↕ HTTP/WS  (localhost)
┌──────────────────────────────────────────────────────┐
│  FASTAPI SERVER  :8000                               │
│  REST  /api/{id}/*   WS  /ws/{id}                    │
│  PROXY /ui/{id}/* → Vite + __HARNESS__ injection     │
└──────────────────────────────────────────────────────┘
         ↕
┌──────────────────────────────────────────────────────┐
│  MAIN PROCESS  (Python)                              │
│  ├─ ComponentTree   (registry)                       │
│  ├─ ProcessManager  (lifecycle)                      │
│  ├─ StateStore      (SQLite persistence)             │
│  ├─ PermissionsGuard (hard enforcement)              │
│  ├─ HarnessLogger   (per-component streams)          │
│  └─ DSPyEngine      (AI brain)                       │
└──────────────────────────────────────────────────────┘
         ↕  HTTP  (localhost)
┌──────────────────────────────────────────────────────┐
│  VITE DEV SERVER  :5173                              │
│  React monorepo — one entry per component_id         │
└──────────────────────────────────────────────────────┘
```

---

## Core rules

1. **Python owns state.** React is stateless beyond UI ephemera (hover, focus, scroll).
2. **One Python component ↔ one React app.** No React app accesses another's state.
3. **Cross-component comms via Python only.** Component A calls `ComponentTree.get("B").on_event(...)`.
4. **View close = process kill. View minimise = process lives.**
5. **Permissions are hard enforced.** Components cannot self-escalate.
6. **Every component has its own log stream** (in-memory ring buffer, exportable to JSON).
7. **StateStore persists across restarts.** Components resume from last saved state.

---

## Data flow: React → Python

```
User clicks button
→ emit("increment", {})           [useHarness hook]
→ WS send {type:"increment", data:{}}
→ FastAPI /ws/{id} receives message
→ component.on_event("increment", {})
→ component.update_state({"count": n+1})
→ _broadcast_ws("state_update", new_state)
→ All connected React clients receive state_update
→ setState(new_state)             [HarnessProvider]
→ React re-renders
```

## Data flow: Python → React (proactive push)

```
Python: await component.emit("alert", {"text": "Job done"})
→ _broadcast_ws("alert", {...})
→ React receives WS message
→ HarnessProvider triggers re-render or custom handler
```

---

## Directory structure

```
vloop-harness/
├── pyproject.toml          UV project + dependencies
├── .env.example            Environment variable template
├── .python-version         Python version pin (3.11)
│
├── harness/                Python package
│   ├── main.py             Entrypoint (typer CLI)
│   ├── window.py           PyWebView wrapper
│   ├── settings.py         Pydantic settings
│   │
│   ├── core/               Core subsystems
│   │   ├── base_component.py
│   │   ├── component_tree.py
│   │   ├── main_process.py
│   │   ├── process_manager.py
│   │   ├── state_store.py
│   │   ├── permissions.py
│   │   └── logger.py
│   │
│   ├── server/             FastAPI layer
│   │   ├── app.py
│   │   ├── injector.py
│   │   └── routes/
│   │       ├── components.py
│   │       ├── proxy.py
│   │       └── ws.py
│   │
│   ├── engine/             DSPy AI engine
│   │   ├── dspy_engine.py
│   │   ├── config.py
│   │   └── modules/
│   │       ├── reasoning.py
│   │       ├── code_gen.py
│   │       ├── qa.py
│   │       └── summarise.py
│   │
│   └── components/         Built-in example components
│       ├── counter.py
│       └── dashboard.py
│
├── react/                  Vite monorepo
│   ├── src/
│   │   ├── harness/        Shared hook + context
│   │   └── components/     One folder per component
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── package.json
│
├── DOCS/                   This documentation
└── tests/                  Pytest test suite
```
