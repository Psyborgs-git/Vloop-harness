# AI Engine (DSPy)

The harness embeds a **DSPy-powered AI engine** as its reasoning core. Every component can call it via `self._main_process.ai`.

---

## Architecture

```
DSPyEngine
├── configure()          Wires up the LM provider (Anthropic / OpenAI / Ollama)
├── run(module, **kw)    Async wrapper around any DSPy module
│
├── reason(question, context)          ChainOfThoughtReasoner
├── generate_code(lang, spec, ctx)     CodeGenerator
├── answer(question, documents)        QuestionAnswerer
├── summarise(text, max_words)         Summariser
│
└── complete(prompt)     Raw LM completion (escape hatch)
```

The engine runs DSPy calls in a **thread-pool executor** so they never block the FastAPI event loop.

---

## Configuration

Set in `.env`:

```env
DSPY_LM_PROVIDER=anthropic          # anthropic | openai | ollama
DSPY_LM_MODEL=claude-sonnet-4-6     # Model name for the chosen provider
ANTHROPIC_API_KEY=sk-ant-...
```

### Supported providers

| Provider | Env var | Example model |
|----------|---------|---------------|
| `anthropic` | `ANTHROPIC_API_KEY` | `claude-sonnet-4-6` |
| `openai` | `OPENAI_API_KEY` | `gpt-4o` |
| `ollama` | `OLLAMA_BASE_URL` | `llama3.2` |

---

## Using the engine in a component

```python
from harness.core.base_component import BaseComponent
from harness.core.permissions import Permission

class SmartComponent(BaseComponent):
    default_permissions = {Permission.AI_INFERENCE}

    async def on_event(self, name, payload):
        mp = self._main_process

        # Chain-of-thought reasoning
        if name == "analyse":
            result = await mp.ai.reason(
                question="What should the user do next?",
                context=str(self.state),
            )
            await self.update_state({"suggestion": result.answer})

        # Code generation
        elif name == "generate_code":
            result = await mp.ai.generate_code(
                language="Python",
                specification=payload["spec"],
            )
            await self.update_state({"code": result.code})

        # Q&A over documents
        elif name == "ask":
            result = await mp.ai.answer(
                question=payload["question"],
                documents=payload.get("docs", ""),
            )
            await self.update_state({"answer": result.answer, "confidence": result.confidence})

        # Summarise
        elif name == "summarise":
            result = await mp.ai.summarise(text=payload["text"], max_words=80)
            await self.update_state({"summary": result.summary})
```

---

## Built-in DSPy modules

### `ChainOfThoughtReasoner`

Signature: `context, question → reasoning, answer`

```python
from harness.engine.modules.reasoning import ChainOfThoughtReasoner

reasoner = ChainOfThoughtReasoner()
result = reasoner(question="Why is the sky blue?")
print(result.reasoning)
print(result.answer)
```

### `CodeGenerator`

Signature: `language, specification, context → code, explanation`

```python
from harness.engine.modules.code_gen import CodeGenerator

gen = CodeGenerator()
result = gen(language="TypeScript", specification="A React hook that debounces a value")
print(result.code)
```

### `QuestionAnswerer`

Signature: `documents, question → answer, confidence`

```python
from harness.engine.modules.qa import QuestionAnswerer

qa = QuestionAnswerer()
result = qa(documents="The Eiffel Tower is in Paris...", question="Where is the Eiffel Tower?")
print(result.answer)      # Paris
print(result.confidence)  # high — directly stated in documents
```

### `Summariser`

Signature: `text, max_words → summary, key_points`

```python
from harness.engine.modules.summarise import Summariser

s = Summariser()
result = s(text="Long article...", max_words=50)
print(result.summary)
print(result.key_points)
```

---

## Running a custom DSPy module

```python
import dspy
from harness.engine.dspy_engine import DSPyEngine

class MySignature(dspy.Signature):
    """Custom task."""
    input_text: str = dspy.InputField()
    output: str = dspy.OutputField()

class MyModule(dspy.Module):
    def __init__(self):
        self.predict = dspy.Predict(MySignature)

    def forward(self, input_text):
        return self.predict(input_text=input_text)

# In a component:
result = await self._main_process.ai.run(MyModule(), input_text="Hello")
print(result.output)
```

---

## DSPy optimisation (optional)

DSPy supports automatic prompt optimisation via `teleprompters`. Example with `BootstrapFewShot`:

```python
import dspy
from dspy.teleprompt import BootstrapFewShot
from harness.engine.modules.reasoning import ChainOfThoughtReasoner

trainset = [
    dspy.Example(question="2+2?", answer="4").with_inputs("question"),
    # ... more examples
]

def metric(example, pred, trace=None):
    return example.answer.lower() in pred.answer.lower()

teleprompter = BootstrapFewShot(metric=metric)
optimised = teleprompter.compile(ChainOfThoughtReasoner(), trainset=trainset)
```

Save and reload optimised modules with `module.save()` / `module.load()`.

---

## Caching

Set `cache_enabled=true` (default) in `.env`. DSPy caches LM responses in `.harness/dspy_cache/` keyed by the exact prompt. This dramatically reduces API costs during development.

To clear the cache:
```bash
rm -rf .harness/dspy_cache
```
