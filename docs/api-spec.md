# API Specification — inference-backend

Base URL: `http://localhost:47201`

## REST Endpoints

### Health

```
GET /health
```
Response:
```json
{ "status": "ok", "uptime_s": 42.1, "lm_provider": "ollama", "lm_model": "llama3" }
```

### Inference

```
POST /infer
```
Body:
```json
{ "module": "my_module", "inputs": { "question": "..." } }
```

### Agent

```
POST /agent/run
```
Body:
```json
{
  "agent": "react",
  "task": "Summarise the file README.md",
  "config": { "max_steps": 10 }
}
```
Response:
```json
{ "run_id": "uuid", "answer": "...", "steps": [...] }
```

```
GET /agent/loops
```
Response: `["react", "chain_of_thought", "plan_execute", "tool_call", "multi_agent"]`

### Pipeline

```
POST /pipeline/create    { name, definition: PipelineSpec }
POST /pipeline/run       { name, inputs }
GET  /pipeline/list
POST /pipeline/rollback  { name, version }
```

### Module

```
POST /module/create   { name, code }
GET  /module/list
POST /module/rollback { name, version }
```

## WebSocket

```
WS /stream
```

### Message Types

```jsonc
// Agent step (thought, action, observation, answer)
{
  "type": "agent.step",
  "id": "<uuid>",
  "timestamp": "2026-01-01T00:00:00Z",
  "payload": {
    "run_id": "<uuid>",
    "step_index": 1,
    "step_type": "thought",
    "content": "I need to read the file first."
  }
}

// Tool call
{
  "type": "agent.tool_call",
  "id": "<uuid>",
  "timestamp": "...",
  "payload": {
    "run_id": "<uuid>",
    "tool_name": "file_rw",
    "inputs": { "path": "README.md", "mode": "read" },
    "outputs": { "content": "..." },
    "duration_ms": 12,
    "status": "success"
  }
}

// Completion
{
  "type": "agent.complete",
  "id": "<uuid>",
  "timestamp": "...",
  "payload": {
    "run_id": "<uuid>",
    "answer": "The README describes...",
    "total_steps": 3,
    "total_tokens": 512
  }
}

// Error
{
  "type": "agent.error",
  "id": "<uuid>",
  "timestamp": "...",
  "payload": {
    "run_id": "<uuid>",
    "error": "Tool execution failed",
    "traceback": "..."
  }
}

// Token stream (for streaming inference)
{
  "type": "infer.token",
  "id": "<uuid>",
  "timestamp": "...",
  "payload": {
    "token": "Hello",
    "finish_reason": null
  }
}
```
