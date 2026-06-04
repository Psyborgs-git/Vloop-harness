# Data Flow and State Management

This document details how data is persisted, cached, and managed across the Vloop Harness lifecycle. The backend leverages SQLAlchemy 2.0+ with `asyncio` (`asyncpg` for PostgreSQL or `aiosqlite` for local SQLite) to manage state.

## Entity Relationship Diagram

The following diagram illustrates the primary data models that drive the Vloop Harness state.

```mermaid
erDiagram
    ChatSession ||--o{ ChatMessage : "contains"
    ChatSession {
        string id PK
        string title
        string provider_id
        datetime created_at
    }

    ChatMessage {
        string id PK
        string session_id FK
        string role
        text content
        datetime created_at
    }

    AgentRun ||--o{ AgentRunStep : "executes"
    AgentRun {
        string id PK
        text goal
        text plan
        string status
        string autonomy_mode
        string session_id FK
    }

    AgentRunStep {
        string id PK
        string run_id FK
        string step_type
        string tool_name
        json input_data
        string status
    }

    AppManifest ||--|{ GeneratedView : "renders"
    AppManifest {
        string id PK
        string name
        string backend_type
        json react_views
        json state_schema
        string status
    }

    ToolTrace {
        string id PK
        string tool_name
        string component_id FK
        json inputs
        json outputs
        string risk_level
        boolean success
    }

    ComponentVersion {
        string id PK
        string component_id FK
        int version_number
        text change_summary
    }
```

## Lifecycle of Core Entities

### 1. Agent Runs
The `AgentRun` model is the centerpiece of the AI execution lifecycle.
*   **Creation:** An agent run is initialized (status: `pending`) when a user requests a complex task via the chat interface or an API trigger.
*   **Execution:** As the DSPy agent plans and executes, `AgentRunStep` records are appended. This provides a strict, append-only audit log of what the AI is thinking, what tools it is calling, and what data it is receiving. The run status changes to `running`.
*   **Completion/Failure:** Upon successful conclusion, the status is marked `completed` and the final JSON structure is saved to the `result` field. If an unrecoverable error occurs, the status becomes `failed` with the traceback saved in the `error` field.

### 2. Tool Traces
For security and auditing, every execution of a system tool (filesystem, database, terminal, browser) is recorded in the `ToolTrace` table.
*   Secrets are redacted before storage.
*   Outputs are truncated at 8KiB to prevent database bloat.
*   If the tool required Human-in-the-Loop (HITL) authorization, the `confirmation_token` is logged to prove the user approved the risk level (`safe`, `caution`, `destructive`).

### 3. App Manifests
`AppManifest` records tie the Cognitive Engine (Layer 1) to the Dynamic Userland (Layer 2).
*   When the AI generates a new pipeline or component, it creates an `AppManifest` linking the backend logic (`backend_id`) to the generated React views (`react_views`).
*   The `state_schema` enforces the expected JSON data contract between the frontend React code and the backend Python code.

## Concurrency and State

*   **Async Operations:** All database calls utilize `sqlalchemy[asyncio]`. This prevents heavy AI processing or slow SQLite writes from blocking the FastAPI event loop.
*   **Atomic Operations:** Critical writes, such as appending an `AgentRunStep` during an active run, are handled transactionally to ensure the audit log remains consistent even if the python process crashes.
*   **Vector Store:** Unstructured data, embeddings, and RAG (Retrieval-Augmented Generation) documents are stored in a separate backend utilizing `sqlite-vec`. This runs in parallel to the relational state DB.