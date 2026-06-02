## 2025-02-23 - [Fix XSS Vulnerability in Injector]
**Vulnerability:** In `harness/server/injector.py`, user-controlled state (`initial_state`) was being serialized via `json.dumps()` and injected directly into an inline `<script>` tag within the HTML response. If a string in `initial_state` contained `</script>`, it could prematurely close the script tag, leading to a Cross-Site Scripting (XSS) vulnerability.
**Learning:** `json.dumps` natively escapes many characters but doesn't escape HTML-specific ones like `<`, `>`, and `&`. Injecting raw JSON directly into HTML (even inside a `<script>` tag) is dangerous and breaks out of the context.
**Prevention:** Always replace sensitive HTML characters (`<`, `>`, `&`) with their unicode escapes (`\u003c`, `\u003e`, `\u0026`) after serialization when embedding JSON in a `<script>` tag.
## 2024-06-11 - SSRF Vulnerability in BrowserTool Prefix Matching
**Vulnerability:** The `BrowserTool`'s origin verification allowed SSRF bypasses because it used `url.startswith(prefix)` to check against allowed origins. An allowed prefix like `http://localhost` could be bypassed by a URL like `http://localhost.evil.com`.
**Learning:** Naive string prefix matching is inherently insecure for URL validation. It does not enforce domain or path boundaries correctly.
**Prevention:** Always use proper URL parsing utilities like `urllib.parse.urlparse` and independently validate the scheme, hostname, port, and path to ensure exact matches.
## 2024-06-01 - Audit Logging for Tool Execution
**Vulnerability:** Missing audit logs for tool executions. Tool actions (like filesystem reads/writes, terminal commands) were executing without a centralized trace record, meaning potentially destructive actions lacked accountability or observability.
**Learning:** The database repository already had a `ToolTrace` model and `record_tool_trace` function, and a robust `redact_secrets` utility existed, but the integration in the central tool dispatcher (`ToolRegistry.execute`) was missing.
**Prevention:** Always ensure that sensitive and potentially destructive actions triggered by users or AI agents are recorded in an audit log with robust secret redaction.
## 2025-02-23 - [Fix SQL Injection Bypass via AST Parsing]
**Vulnerability:** The `DatabaseTool` used regexes like `^\s*SELECT\b` and `^\s*(INSERT|UPDATE|DELETE)\b` to validate SQL queries for `query_read` and `query_write` operations. This allowed bypassing validation via statement chaining (e.g. `WITH cte AS (SELECT 1) SELECT * FROM cte; UPDATE users SET role='admin'`).
**Learning:** Regex is inherently unsuited for robust SQL query validation because it cannot accurately parse statement boundaries or understand complex structures like CTEs.
**Prevention:** Always use a proper Abstract Syntax Tree (AST) parser like `sqlglot` to parse and validate every statement in a given SQL query block instead of using naive regex.
