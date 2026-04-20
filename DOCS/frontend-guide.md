# Frontend Guide

## Project structure

```
react/
├── src/
│   ├── harness/                    Shared harness primitives
│   │   ├── types.ts                TypeScript type definitions
│   │   ├── HarnessProvider.tsx     Context provider (WebSocket, state)
│   │   └── useHarness.ts           Consumer hook
│   │
│   └── components/
│       ├── root/                   Root window manager (special)
│       │   ├── main.tsx
│       │   └── App.tsx
│       │
│       └── <component_id>/         One folder per Python component
│           ├── main.tsx
│           └── App.tsx
│
├── vite.config.ts                  Multi-entry build
├── tsconfig.json
└── package.json
```

---

## Adding a new component UI

1. Create `react/src/components/<component_id>/main.tsx`:

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

2. Create `react/src/components/<component_id>/App.tsx` with your UI.

3. Vite auto-discovers the entry (see `vite.config.ts` `discoverEntries()`).

---

## window.__HARNESS__

Injected into `<head>` by the FastAPI proxy before serving:

```typescript
interface HarnessConfig {
  COMPONENT_ID: string;      // "comp_abc123"
  API_URL: string;           // "http://localhost:8000/api/comp_abc123"
  WS_URL: string;            // "ws://localhost:8000/ws/comp_abc123"
  INITIAL_STATE: Record<string, unknown>;
  PERMISSIONS: string[];
}
```

Available as `window.__HARNESS__` globally. The `HarnessProvider` reads this automatically — you don't need to touch it directly.

---

## HarnessProvider

Wrap your app's root:

```tsx
<HarnessProvider>
  <App />
</HarnessProvider>
```

Internally it:
1. Opens a WebSocket to `WS_URL`
2. Initialises state from `INITIAL_STATE`
3. Listens for `state_update` messages and calls `setState`
4. Reconnects automatically after disconnect (1 s back-off)
5. Sends `{ type: "reloading" }` awareness

---

## useHarness hook

```typescript
const { state, emit, props, connected } = useHarness();
```

### state

Live mirror of the Python component's `state` dict. Automatically updated whenever Python calls `update_state()`.

```tsx
<p>Count: {state.count as number}</p>
```

### emit

Send a named event to the Python component. Python receives it in `on_event(name, payload)`.

```tsx
<button onClick={() => emit("increment")}>+</button>
<button onClick={() => emit("set_label", { text: "hello" })}>Label</button>
```

### props

Read-only props passed from the Python parent. Reflects `component.props`.

### connected

`true` when the WebSocket is open. Use for status indicators:

```tsx
{!connected && <div className="banner">Reconnecting…</div>}
```

---

## TypeScript path alias

`@harness/*` resolves to `src/harness/*` via `tsconfig.json` and `vite.config.ts`:

```typescript
import { useHarness } from "@harness/useHarness";
import type { HarnessContext } from "@harness/types";
```

---

## Production build

```bash
cd react
npm run build
```

Output goes to `react/dist/`. The FastAPI proxy will serve these static files instead of forwarding to Vite when `HARNESS_DEBUG=false`.
