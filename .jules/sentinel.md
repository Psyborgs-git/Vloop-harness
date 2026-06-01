## 2024-06-01 - Audit Logging for Tool Execution
**Vulnerability:** Missing audit logs for tool executions. Tool actions (like filesystem reads/writes, terminal commands) were executing without a centralized trace record, meaning potentially destructive actions lacked accountability or observability.
**Learning:** The database repository already had a `ToolTrace` model and `record_tool_trace` function, and a robust `redact_secrets` utility existed, but the integration in the central tool dispatcher (`ToolRegistry.execute`) was missing.
**Prevention:** Always ensure that sensitive and potentially destructive actions triggered by users or AI agents are recorded in an audit log with robust secret redaction.
