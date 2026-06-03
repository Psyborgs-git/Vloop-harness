# Vloop Harness — Developer Reference

## Overview
This harness is a local-first AI engineering workbench with a comprehensive DSPy pipeline framework, dynamic AI engine, vector store / RAG, self-improving optimization, and memory management.

## New Infrastructure (added 2025-05-23)

### 1. Dynamic AI Engine
- **Model Registry** (`harness/engine/model_registry.py`): Static catalog for Anthropic, OpenAI, Ollama models with metadata (context window, pricing, capabilities). Dynamic Ollama discovery via `/api/tags`.
- **Model Router** (`harness/engine/model_router.py`): Intelligent routing with fallback chains, health tracking, and strategies: EXACT, CAPABILITY, PROVIDER, FASTEST.
- **Dynamic Config** (`harness/engine/dynamic_config.py`): Runtime parameter adaptation — auto `max_tokens` from context window, temperature by task type, token counting via tiktoken.

### 2. Vector Store / RAG
- **Embeddings** (`harness/engine/vector_store/embeddings.py`): OpenAI API, Ollama, local sentence-transformers.
- **Store Backends** (`harness/engine/vector_store/store.py`): `SqliteVecStore` (sqlite-vec) with `InMemoryVecStore` fallback.
- **Retriever** (`harness/engine/vector_store/retriever.py`): DSPy-compatible retriever module with document chunking.

### 3. Reusable Pipeline Framework
- **Base** (`harness/engine/pipelines/base.py`): DAG nodes, edges, conditional branching, loops, map/reduce.
- **Executor** (`harness/engine/pipelines/executor.py`): Async DAG execution with parallel branch support.
- **Templates** (`harness/engine/pipelines/templates.py`):
  - `SequentialPipeline` — linear execution
  - `RAGPipeline` — retrieve → generate
  - `MapReducePipeline` — parallel map with reduce
  - `AgentLoopPipeline` — think → act → observe → (continue|stop)
  - `ReflectionPipeline` — generate → critique → revise

### 4. Self-Improving Harness
- **Optimizer** (`harness/engine/optimization/optimizer.py`): DSPy teleprompter wrapper (BootstrapFewShot, MIPROv2 fallback).
- **Evaluator** (`harness/engine/optimization/evaluator.py`): Evaluation runner with metrics (exact_match, contains, length_ratio).
- **Feedback** (`harness/engine/optimization/feedback.py`): User feedback collection stored in `.vloop/feedback/` JSONL.
- **Self-Improvement Loop** (`harness/engine/optimization/self_improve.py`): Orchestrates generate → compile → evaluate → optimize → iterate.

### 5. Memory
- **Conversation Memory** (`harness/engine/memory/conversation.py`): Sliding window + summarization for long conversations.
- **Working Memory** (`harness/engine/memory/working.py`): Key-value scratchpad for agent runs.

## Integration Points

### DSPyEngine
All new subsystems are wired into `DSPyEngine`:
- `engine.model_registry` / `engine.model_router` / `engine.dynamic_config`
- `engine.vector_store` / `engine.embedder`
- `engine.self_improvement`
- `engine.conversation_memory` / `engine.working_memory`

New methods:
- `await engine.route_and_run(module, model_id, capabilities, **kwargs)`
- `await engine.run_with_dynamic_config(module, prompt_text, task_type, **kwargs)`
- `await engine.retrieve_and_answer(query, top_k)`
- `await engine.improve_component(module, module_name, trainset)`
- `await engine.generate_and_improve(spec)`

### App Factory
`harness/server/app.py` bootstraps vector store (sqlite-vec with fallback) and discovers Ollama models at startup.

### New REST Routes
- `/api/pipelines/*` — build, run, validate DAG pipelines
- `/api/optimization/*` — improve, evaluate, feedback, compare
- `/api/vector-store/*` — add documents, semantic search, clear

## Dependencies
Added to `pyproject.toml`:
- `sqlite-vec>=0.1.0`
- `sentence-transformers>=3.0.0`
- `tiktoken>=0.8.0`

## Testing
New test files:
- `tests/test_model_registry.py`
- `tests/test_vector_store.py`
- `tests/test_pipelines.py`
- `tests/test_optimization.py`

Run all tests: `pytest tests/`

## Verification
```bash
source .venv/bin/activate
python -c "from harness.engine.dspy_engine import DSPyEngine; print('OK')"

# Run specific new test modules
pytest tests/test_model_registry.py tests/test_vector_store.py tests/test_pipelines.py tests/test_optimization.py tests/test_e2e_integration.py -v

# Run full test suite (420 tests, all passing)
pytest tests/ --ignore=tests/test_resource_monitor.py -v
```

## Test Results
- **420 tests passed** (409 unit/integration + 11 e2e integration)
- **0 failures**
- Pre-existing bugs fixed:
  - `diff_utils.py` — `difflib.unified_diff` rejected `None` for `fromfiledate`/`tofiledate` in Python 3.11
  - `eval_routes.py` — `field_results` was computed but not included in the response

## Build Commands
```bash
# Rust core
cargo build --manifest-path harness-core/Cargo.toml --release

# React frontend
cd react && npm run typecheck && npm run build

# Start backend (Python only)
source .venv/bin/activate
harness internal backend-worker --host localhost --port 9100

# Run native app (Rust binary with native window)
./harness-core/target/release/vloop-harness run

# Run headless (no window, static frontend)
./harness-core/target/release/vloop-harness run --no-window --frontend-mode static
```
