# API Reference

Base URL: `http://localhost:8000`

---

## Static endpoints

### `GET /`

Health check.

**Response**
```json
{"status": "ok", "service": "vloop-harness"}
```

---

### `GET /api/components`

List all running components.

**Response** — array of component snapshots:
```json
[
  {
    "id": "comp_a1b2c3d4",
    "state": {"count": 5},
    "props": {},
    "permissions": ["ui.resize"]
  }
]
```

---

### `POST /api/components`

Create a new component at runtime.

**Request body**
```json
{
  "class_path": "harness.components.counter.CounterComponent",
  "props": {"initial": 10},
  "permissions": ["ui.resize"]
}
```

**Response** — component snapshot (201 Created)

---

### `DELETE /api/components/{component_id}`

Destroy a component. Calls `on_unmount()` and removes all routes.

**Response** — 204 No Content

---

## Dynamic component endpoints

These are available for any registered `{component_id}`.

### `GET /api/{component_id}/state`

Fetch current state snapshot.

**Response** — component snapshot

---

### `POST /api/{component_id}/event`

Send an event from HTTP (alternative to WebSocket).

**Request body**
```json
{"name": "increment", "payload": null}
```

**Response**
```json
{"status": "ok"}
```

---

### `POST /api/{component_id}/props`

Push updated props to a component.

**Request body**
```json
{"props": {"label": "Updated"}}
```

**Response**
```json
{"status": "ok"}
```

---

### `GET /api/{component_id}/logs`

Tail component log stream.

**Query params**
- `n` — number of entries (default: 100)

**Response** — array of log entries:
```json
[
  {"level": "INFO", "message": "Component mounted", "component": "comp_abc123"}
]
```

---

## WebSocket

### `WS /ws/{component_id}`

Bidirectional event stream. Connect once per component view.

**On connect** — server immediately sends:
```json
{"type": "state_update", "data": { /* current state */ }}
```

**Client → Server** (send events):
```json
{"type": "increment", "data": null}
{"type": "load", "data": {"query": "…"}}
```

**Server → Client** (receive events):
```json
{"type": "state_update", "data": {…}}
{"type": "reloading", "data": {}}
{"type": "<custom_event>", "data": {…}}
```

---

## UI serving

### `GET /ui/{component_id}/`

Serves the Vite-built React app for a component, with `window.__HARNESS__` injected into `<head>`:

```javascript
window.__HARNESS__ = {
  COMPONENT_ID: "comp_abc123",
  API_URL: "http://localhost:8000/api/comp_abc123",
  WS_URL: "ws://localhost:8000/ws/comp_abc123",
  INITIAL_STATE: { "count": 5 },
  PERMISSIONS: ["ui.resize"]
}
```
