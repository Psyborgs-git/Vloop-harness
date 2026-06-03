# Component Development Guide

## Python component

Every component is a class that inherits `BaseComponent`.

```python
from harness.core.base_component import BaseComponent
from harness.core.permissions import Permission
from typing import Any

class MyComponent(BaseComponent):
    # Declare required permissions at class level
    default_permissions = {Permission.UI_RESIZE, Permission.AI_INFERENCE}

    async def on_mount(self) -> None:
        """Called when the view opens. Set initial state here."""
        await self.update_state({"items": [], "loading": False})

    async def on_unmount(self) -> None:
        """Called on view close. Release resources."""

    async def on_hide(self) -> None:
        """Called on minimise. Process stays alive."""

    async def on_show(self) -> None:
        """Called when view is restored."""

    async def on_update(self, new_props: dict) -> None:
        """Parent pushed new props."""
        await super().on_update(new_props)  # merges into self.props

    async def on_event(self, name: str, payload: Any) -> None:
        """React emitted an event."""
        if name == "load":
            await self._load_data()

    async def _load_data(self) -> None:
        await self.update_state({"loading": True})
        # ... do work ...
        await self.update_state({"items": [...], "loading": False})
```

### State management

`update_state(patch)` merges the patch dict into `self.state` **and** pushes a `state_update` message to all connected React clients atomically.

```python
# Good — single round-trip
await self.update_state({"count": 5, "label": "done"})

# Avoid — two round-trips
await self.update_state({"count": 5})
await self.update_state({"label": "done"})
```

### Emitting events to React

```python
# Push a named event (non-state notification)
await self.emit("job_complete", {"duration_ms": 120})
```

### Cross-component communication

```python
async def on_event(self, name, payload):
    if name == "forward_to_dashboard":
        mp = self._main_process
        dashboard = mp.get_component("dashboard_id")
        if dashboard:
            await dashboard.on_event("metric_update", payload)
```

### Using the AI engine

```python
async def on_event(self, name, payload):
    if name == "analyse":
        mp = self._main_process
        result = await mp.ai.reason(
            question="What does this data indicate?",
            context=str(self.state),
        )
        await self.update_state({"analysis": result.answer})
```

---

## React app

Each component has its own React app in `react/src/components/<component_id>/`.

### Minimum files

```
react/src/components/my_component/
├── main.tsx    ← entry point (mount root)
└── App.tsx     ← root component
```

### main.tsx

```tsx
import React from "react";
import { createRoot } from "react-dom/client";
import { HarnessProvider } from "@harness/HarnessProvider";
import App from "./App";

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <HarnessProvider>
      <App />
    </HarnessProvider>
  </React.StrictMode>
);
```

### App.tsx

```tsx
import { useHarness } from "@harness/useHarness";

export default function App() {
  const { state, emit, connected } = useHarness();

  return (
    <div>
      <p>Status: {connected ? "live" : "connecting..."}</p>
      <p>Count: {String(state.count ?? 0)}</p>
      <button onClick={() => emit("increment")}>+</button>
      <button onClick={() => emit("decrement")}>−</button>
    </div>
  );
}
```

### useHarness hook

```typescript
const { state, emit, props, connected } = useHarness();
```

| Field | Type | Description |
|-------|------|-------------|
| `state` | `Record<string, unknown>` | Live Python state — auto-updated via WS |
| `props` | `Record<string, unknown>` | Read-only props from Python parent |
| `emit` | `(name: string, payload?: unknown) => void` | Send event to Python |
| `connected` | `boolean` | True when WebSocket is open |

---

## Permissions

Declare permissions at class level to give the harness a manifest:

```python
class MyComponent(BaseComponent):
    default_permissions = {
        Permission.FILESYSTEM_READ,
        Permission.NETWORK_OUTBOUND,
        Permission.AI_INFERENCE,
    }
```

Available permissions:

| Permission | Capability |
|-----------|-----------|
| `filesystem.read` | Read files from disk |
| `filesystem.write` | Write files to disk |
| `network.outbound` | Make outbound HTTP requests |
| `network.inbound` | Open ports / receive connections |
| `shell.exec` | Run terminal commands |
| `ipc.broadcast` | Send events to other components |
| `ipc.receive` | Receive events from other components |
| `state.persist` | Write state to disk |
| `ui.resize` | Resize own view |
| `ui.spawn` | Create child components |
| `ai.inference` | Use the AI engine |

Permissions can be granted/revoked at runtime by `MainProcess.permissions`:

```python
main_process.permissions.grant(component_id, Permission.NETWORK_OUTBOUND)
main_process.permissions.revoke(component_id, Permission.SHELL_EXEC)
```

---

## Hot reload

### Python

The `ProcessManager.hot_reload()` method reimports a component class from disk without restarting the entire harness:

```python
await process_manager.hot_reload(component, Path("harness/components/my_comp.py"))
```

State is preserved across hot reload.

### React

Vite HMR works automatically. Edit any `.tsx` file and the iframe updates instantly.
