# Quickstart

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | ≥ 3.11 | Runtime |
| [uv](https://docs.astral.sh/uv/) | latest | Python package manager |
| Node.js | ≥ 20 | Vite / React |
| npm | ≥ 10 | React deps |

---

## 1 — Clone and install

```bash
git clone https://github.com/psyborgs-git/vloop-harness
cd vloop-harness

# Python deps (uv resolves and locks automatically)
uv sync

# React / Vite deps
cd react && npm install && cd ..
```

---

## 2 — Configure environment

```bash
cp .env.example .env
# Edit .env — at minimum set ANTHROPIC_API_KEY
```

---

## 3 — Run

```bash
# Full stack (native window + Vite + API)
uv run harness run

# Headless (no native window — open http://localhost:8000/ui/root in browser)
uv run harness run --no-window

# Skip AI engine (useful when no API key available)
uv run harness run --no-ai --no-window
```

---

## 4 — Create your first component

**Python side** — `harness/components/my_app.py`:

```python
from harness.core.base_component import BaseComponent
from harness.core.permissions import Permission

class MyApp(BaseComponent):
    default_permissions = {Permission.UI_RESIZE}

    async def on_mount(self):
        await self.update_state({"message": "Hello from Python!"})

    async def on_event(self, name, payload):
        if name == "greet":
            await self.update_state({"message": f"Hello, {payload}!"})
```

**React side** — `react/src/components/<component_id>/App.tsx`:

```tsx
import { useHarness } from "@harness/useHarness";

export default function App() {
  const { state, emit } = useHarness();
  return (
    <div>
      <p>{String(state.message)}</p>
      <button onClick={() => emit("greet", "World")}>Greet</button>
    </div>
  );
}
```

Register at runtime via the API:

```bash
curl -X POST http://localhost:8000/api/components \
  -H "Content-Type: application/json" \
  -d '{"class_path": "harness.components.my_app.MyApp", "props": {}}'
```

The Root UI will open a floating view for the new component automatically.

---

## 5 — Use AI in a component

```python
async def on_event(self, name, payload):
    if name == "ask":
        result = await self._main_process.ai.reason(
            question=payload["question"],
            context=str(self.state),
        )
        await self.update_state({"answer": result.answer})
```

See [ai-engine.md](ai-engine.md) for full API reference.
