# HARNESS — Architecture README

A native binary harness where Python components run logic/state/events and pair 1:1 with React UI apps served dynamically from a shared Vite dev server. Components run as mini-apps inside a resizable root window. Python is the brain. React is the face.

-----

## Top-Level Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  NATIVE BINARY (PyInstaller)                                                │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  Root Window (PyWebView)                                             │   │
│  │                                                                      │   │
│  │  ┌─────────────────────────────────────────────────────────────┐     │   │
│  │  │  Root UI  (localhost:3000/root)                             │     │   │
│  │  │                                                             │     │   │
│  │  │  ┌──────────────────┐  ┌──────────────────┐                 │     │   │
│  │  │  │  View A          │  │  View B          │  ...            │     │   │
│  │  │  │  /ui/comp_a/     │  │  /ui/comp_b/     │                 │     │   │
│  │  │  │                  │  │                  │                 │     │   │
│  │  │  │  [React App A]   │  │  [React App B]   │                 │     │   │
│  │  │  │                  │  │                  │                 │     │   │
│  │  │  │  [resize/move]   │  │  [minimise/close]│                 │     │   │
│  │  │  └──────────────────┘  └──────────────────┘                 │     │   │
│  │  └─────────────────────────────────────────────────────────────┘     │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  MainProcess (Python)                                                │   │
│  │  ├─ ComponentTree                                                    │   │
│  │  ├─ ProcessManager                                                   │   │
│  │  ├─ PermissionsGuard                                                 │   │
│  │  ├─ StateStore                                                       │   │
│  │  └─ Logger                                                           │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  FastAPI Server                                                      │   │
│  │  ├─ REST  /api/{component_id}/*                                      │   │
│  │  ├─ WS    /ws/{component_id}                                         │   │
│  │  └─ SERVE /ui/{component_id}/{*react_routes}  (injects env vars)     │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  Vite Dev Server  (localhost:5173)                                   │   │
│  │  ├─ Single React monorepo                                            │   │
│  │  ├─ One entry per component: src/components/{component_id}/App.tsx   │   │
│  │  └─ Hot module reload on file change                                 │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

-----

## Python Component System

### BaseComponent

Every component inherits from `BaseComponent`. Pure Python — no UI code.

```
BaseComponent
├── id: str                     (auto-generated UUID)
├── props: dict                 (passed from parent or MainProcess)
├── state: dict                 (internal, managed by Python)
├── children: list[BaseComponent]
├── permissions: PermissionSet
│
├── on_mount()                  → called when view opens
├── on_unmount()                → called when view is closed (hard)
├── on_hide()                   → called when view is minimised
├── on_show()                   → called when view is restored
├── on_update(new_props)        → called when parent pushes new props
├── on_event(name, payload)     → called when React emits event
│
├── emit(name, payload)         → push event to paired React UI
├── update_state(patch)         → merge patch into state, notify React
├── get_snapshot()              → return serialisable state dict
└── cleanup()                   → release resources, kill threads
```

### Component Lifecycle

```
CREATE
  ↓
MainProcess.register(component)
  ↓
ProcessManager.start(component)     → on_mount()
  ↓
FastAPI registers /api/{id}/* routes
FastAPI registers /ws/{id}
  ↓
RootUI told: "mount view for {id}"
  ↓
View iframe loads /ui/{id}/
  ↓
Vite serves HTML with injected:
  COMPONENT_ID, API_URL, WS_URL, INITIAL_STATE
  ↓
React app boots, connects WS, renders UI
  ↓
RUNNING (events flow both ways)

────────── HIDE (minimise) ──────────
RootUI hides iframe (display:none)
Component.on_hide()
Process stays alive. State preserved.

────────── SHOW (restore) ───────────
RootUI shows iframe
Component.on_show()
React re-syncs state via WS

────────── CLOSE (unmount) ──────────
RootUI removes iframe
Component.on_unmount()
Component.cleanup()
ProcessManager.stop(component)
FastAPI removes routes for {id}
StateStore flushes component state
Logger records shutdown
```

-----

## MainProcess

Owns everything. Single entrypoint.

```
MainProcess
│
├── ComponentTree
│   ├── root: RootComponent
│   ├── register(component)
│   ├── unregister(component_id)
│   ├── get(component_id)
│   ├── list_all()
│   └── broadcast(event)           → sends to all components
│
├── ProcessManager
│   ├── start(component)           → on_mount + route registration
│   ├── stop(component)            → on_unmount + cleanup
│   ├── restart(component)         → stop → start (hot reload)
│   ├── list_running()
│   └── watchdog()                 → monitor crashed components
│
├── StateStore
│   ├── set(component_id, key, val)
│   ├── get(component_id, key)
│   ├── persist()                  → save to disk (JSON/SQLite)
│   ├── restore()                  → load from disk on boot
│   └── flush(component_id)        → clear on unmount
│
├── PermissionsGuard
│   ├── PermissionSet per component (filesystem, network, shell, ipc)
│   ├── check(component_id, permission)
│   ├── grant(component_id, permission)
│   └── revoke(component_id, permission)
│
└── Logger
    ├── Per-component log streams
    ├── Log levels: DEBUG, INFO, WARN, ERROR
    ├── log(component_id, level, message)
    ├── tail(component_id, n)
    └── export(component_id, path)
```

-----

## FastAPI Layer

Single server. Routes dynamically registered per component.

```
Static Routes:
  GET  /                          → root window HTML
  GET  /api/components            → list all running components
  POST /api/components            → create new component (runtime)
  DELETE /api/components/{id}     → destroy component

Dynamic Routes (registered on component mount):
  GET  /api/{component_id}/state          → current state snapshot
  POST /api/{component_id}/event          → React → Python event
  POST /api/{component_id}/props          → update props from parent
  WS   /ws/{component_id}                 → bidirectional event stream

UI Serving:
  GET  /ui/{component_id}/{*react_routes}
       → FastAPI proxies Vite dev server
       → Injects into <head>:
           window.__HARNESS__ = {
             COMPONENT_ID: "{id}",
             API_URL: "http://localhost:8000/api/{id}",
             WS_URL:  "ws://localhost:8000/ws/{id}",
             INITIAL_STATE: {...},
             PERMISSIONS: [...]
           }
```

-----

## Vite / React Layer

Single Vite monorepo. One shared dev server. Each component has its own React app entry.

```
react/
├── src/
│   ├── harness/
│   │   ├── useHarness.ts       → hook: connects WS, exposes state + emit
│   │   ├── HarnessProvider.tsx → context: wraps app with WS connection
│   │   └── types.ts            → shared types
│   │
│   └── components/
│       ├── {component_id_a}/
│       │   ├── App.tsx         → root of React app for this component
│       │   └── *.tsx           → any custom UI files
│       │
│       └── {component_id_b}/
│           ├── App.tsx
│           └── ...
│
├── vite.config.ts              → multi-entry: each component_id = own entry
└── package.json
```

### useHarness Hook (available in every React app)

```typescript
const { state, emit, props } = useHarness()

// state   → live Python state (auto-updated via WS)
// emit    → send event to Python:  emit("click", { x, y })
// props   → read-only props from Python parent
```

### HTML Injection (FastAPI does this at serve time)

```html
<script>
  window.__HARNESS__ = {
    COMPONENT_ID: "comp_abc123",
    API_URL: "http://localhost:8000/api/comp_abc123",
    WS_URL:  "ws://localhost:8000/ws/comp_abc123",
    INITIAL_STATE: { "counter": 0 },
    PERMISSIONS: ["read_state", "emit_events"]
  }
</script>
```

React reads `window.__HARNESS__` on boot. No env files needed per component.

-----

## Root UI — Window Manager

Root window is a React app at `/root`. It is the shell. Manages views.

```
RootUI
├── ViewManager
│   ├── views: Map<component_id, ViewState>
│   ├── open(component_id)       → mount iframe, tell Python on_mount
│   ├── close(component_id)      → remove iframe, tell Python on_unmount
│   ├── minimize(component_id)   → hide iframe (display:none), tell Python on_hide
│   └── restore(component_id)    → show iframe, tell Python on_show
│
└── View (per component)
    ├── <iframe src="/ui/{component_id}/" />
    ├── Resizable  (drag corners)
    ├── Moveable   (drag title bar)
    ├── Title bar:
    │   ├── [─]  minimise  → hide view, process lives
    │   └── [✕]  close     → remove view, process dies
    └── Position + size persisted in StateStore
```

Views float freely in the root window. Can overlap, stack, arrange as needed. Root UI has no knowledge of iframe content — that is the paired React app’s concern.

-----

## Inter-Component Communication

React apps never talk to each other. All cross-component comms go through Python.

```
React App A
  → emit("send_data", payload)
  → WS → Python Component A.on_event()
  → Component A calls: MainProcess.ComponentTree.get("comp_b").on_event(...)
  → Python Component B updates state
  → Component B.emit("data_received", payload)
  → WS → React App B re-renders
```

-----

## Hot Reload

### Python Components

```
File watcher monitors /components/*.py
  → Change detected
  → ProcessManager.restart(component)
  → on_unmount() → reimport class → on_mount()
  → State optionally restored from StateStore
  → WS notifies React: { type: "reloading" }
  → React shows loader → reconnects when ready
```

### React UI

```
Vite HMR handles automatically.
  → Edit src/components/{id}/App.tsx
  → Vite pushes update to iframe
  → React hot reloads in place
  → No Python restart needed
```

-----

## Runtime Component Creation

```
1. User opens "New Component" in Root UI
2. Fills: name, permissions, initial props
3. Root UI: POST /api/components
4. MainProcess:
   ├── Instantiates BaseComponent subclass
   ├── Registers in ComponentTree
   └── ProcessManager.start()
5. Vite stub created: src/components/{new_id}/App.tsx
6. FastAPI registers routes for {new_id}
7. Root UI opens view for {new_id}
8. User edits React file in editor (built-in or external)
9. Vite HMR updates live in view
```

-----

## Directory Structure

```
harness/
│
├── main.py                     → entrypoint: boots everything
├── window.py                   → PyWebView root window
│
├── core/
│   ├── base_component.py
│   ├── main_process.py
│   ├── component_tree.py
│   ├── process_manager.py
│   ├── state_store.py
│   ├── permissions.py
│   └── logger.py
│
├── server/
│   ├── app.py                  → FastAPI app
│   ├── routes/
│   │   ├── components.py       → CRUD
│   │   ├── proxy.py            → /ui/{id}/* → Vite proxy + injection
│   │   └── ws.py               → /ws/{id} WebSocket handler
│   └── injector.py             → injects window.__HARNESS__ into HTML
│
├── components/                 → user Python components live here
│   ├── counter.py
│   └── dashboard.py
│
└── react/                      → Vite monorepo
    ├── src/
    │   ├── harness/            → shared hook + context
    │   └── components/         → one folder per component ID
    ├── vite.config.ts
    └── package.json
```

-----

## Startup Sequence

```
1. main.py
   ├── Boot Logger
   ├── Boot StateStore (restore persisted state from disk)
   ├── Boot MainProcess
   ├── Boot ComponentTree (re-register saved components)
   ├── Start FastAPI (uvicorn on background thread)
   ├── Start Vite dev server (subprocess)
   └── Open PyWebView window → loads localhost:8000/root

2. Root UI loads
   ├── Connects WS to MainProcess
   ├── GET /api/components
   └── Restores saved view layout from StateStore

3. Components mount (on_mount per component)

4. Ready
```

-----

## Permissions

Declared per component. Enforced by MainProcess. Components cannot self-escalate.

```
filesystem.read        → read files from disk
filesystem.write       → write files to disk
network.outbound       → make HTTP requests
network.inbound        → open ports / receive
shell.exec             → run terminal commands
ipc.broadcast          → send events to other components
ipc.receive            → receive events from other components
state.persist          → write state to disk
ui.resize              → resize own view
ui.spawn               → create new child components
```

-----

## Core Rules

1. Python is the brain. React renders only.
1. One Python component ↔ one React app. No sharing.
1. Cross-component comms via Python only. React is isolated.
1. View close = process kill. View minimise = process lives.
1. All state lives in Python. React is stateless beyond UI ephemera.
1. Permissions are hard enforced. No self-escalation.
1. Every component has its own log stream.
1. StateStore persists across restarts. Components resume last state.