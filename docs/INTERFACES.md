# Interfaces and Contracts

This document defines the strict communication boundaries and event-driven schemas that allow the three layers of the Vloop Harness to interact safely.

## 1. Rust ↔ Python Inter-Process Communication (IPC)

Because the Rust Kernel (Layer 0) is responsible for execution and secrets, and the Python Engine (Layer 1) handles the AI logic, they must communicate securely.

### Transport
Communication occurs via HTTP POST requests for unidirectional commands and WebSockets for bidirectional streaming.

*   **Rust -> Python:** Rust sends system events and boot configuration (like allocated ports) via HTTP POST to the Python endpoint `/api/ipc/rust_push`.
*   **Python -> Rust:** Python maintains a WebSocket connection to a Tauri-managed secure port to request secure vault keys or to command the execution sandbox.

### Payload Schema: Vault Request (Python -> Rust)

**Input Attributes:**
| Field      | Type     | Description                                |
|------------|----------|--------------------------------------------|
| `type`     | string   | The event type, e.g. `"vault_request"`     |
| `key_name` | string   | The requested key, e.g. `"OPENAI_API_KEY"` |

**Output Attributes:**
| Field      | Type     | Description                                |
|------------|----------|--------------------------------------------|
| `type`     | string   | The event type, e.g. `"vault_response"`    |
| `key_name` | string   | The requested key, e.g. `"OPENAI_API_KEY"` |
| `value`    | string   | The retrieved secret value                 |
| `status`   | string   | e.g. `"success"` or `"error"`              |

### Error Codes (IPC)

| Error Code            | Description                                                                                          |
|-----------------------|------------------------------------------------------------------------------------------------------|
| `401_UNAUTHORIZED`    | Emitted if Python attempts to request a vault key it is not permitted to access.                     |
| `404_NOT_FOUND`       | Emitted if the requested vault key does not exist.                                                   |
| `500_SANDBOX_CRASH`   | Emitted if a `bollard` Docker container or `ssh2` session unexpectedly terminates during execution.  |

## 2. Python ↔ React WebSockets & REST APIs

Layer 2 (React) communicates entirely with Layer 1 (Python). It uses standard REST for CRUD operations and WebSockets for real-time events.

### Transport
*   **REST API:** Hosted by FastAPI (default port `9100`). Defines routes like `/api/chat`, `/api/pipelines`, `/api/agent`.
*   **WebSocket:** Real-time event bus mounted at `/api/ws`.

### Event-Driven Schema: Human-in-the-Loop (HITL) Request

When the AI attempts a destructive action, Python emits a HITL request to React over the WebSocket.

**Python -> React (Emit) Payload Attributes:**
| Field          | Type     | Description                                                                 |
|----------------|----------|-----------------------------------------------------------------------------|
| `token`        | string   | A unique UUID for the HITL request.                                         |
| `tool`         | string   | The tool being executed (e.g., `"terminal"`, `"database"`).                 |
| `command`      | string   | The specific command/query being requested.                                 |
| `risk_level`   | string   | Classification level: `"safe"`, `"caution"`, `"destructive"`.               |
| `reason`       | string   | The AI's explanation for why this action is required.                       |

**React -> Python (Response) Payload Attributes:**
| Field          | Type     | Description                                                                 |
|----------------|----------|-----------------------------------------------------------------------------|
| `token`        | string   | The UUID from the original request.                                         |
| `approved`     | boolean  | Whether the user approved (`true`) or denied (`false`) the request.         |

### Event-Driven Schema: Tool Trace Emission

As the AI works autonomously, it emits tool traces to populate the React timeline UI in real time.

**Python -> React (Emit) Payload Attributes:**
| Field          | Type     | Description                                                                 |
|----------------|----------|-----------------------------------------------------------------------------|
| `trace_id`     | string   | A unique UUID for the trace event.                                          |
| `tool`         | string   | The tool executed.                                                          |
| `status`       | string   | Execution status (e.g., `"completed"`, `"failed"`).                         |
| `duration_ms`  | integer  | Execution time in milliseconds.                                             |
| `summary`      | string   | A brief description of the action taken.                                    |

## 3. Sandboxed Iframe Contracts

When AI-generated React views are injected into the dynamic WorkspaceArea, they communicate with the main React application via the `postMessage` API.

**Iframe -> React Host Message Attributes:**
| Field          | Type     | Description                                                                 |
|----------------|----------|-----------------------------------------------------------------------------|
| `type`         | string   | `"VLOOP_IFRAME_READY"`                                                      |
| `view_id`      | string   | The identifier of the generated view that has finished mounting.            |

**React Host -> Iframe (State Injection) Message Attributes:**
| Field          | Type     | Description                                                                 |
|----------------|----------|-----------------------------------------------------------------------------|
| `type`         | string   | `"VLOOP_UPDATE_STATE"`                                                      |
| `payload`      | object   | An object containing `theme` and dynamic component `data`.                  |