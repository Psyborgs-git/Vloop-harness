# Database Schema

SQLite (default) with WAL mode. Optional Postgres via `DB_ENGINE=postgres`.

## V1 Migration — Initial Schema

```sql
CREATE TABLE agent_runs (
  id TEXT PRIMARY KEY,
  agent_name TEXT NOT NULL,
  agent_loop TEXT NOT NULL,
  task TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('running','completed','failed','cancelled')),
  created_at TEXT NOT NULL,
  finished_at TEXT,
  config_json TEXT
);

CREATE TABLE agent_steps (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
  step_index INTEGER NOT NULL,
  step_type TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE tool_calls (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
  step_id TEXT REFERENCES agent_steps(id),
  tool_name TEXT NOT NULL,
  inputs_json TEXT NOT NULL,
  outputs_json TEXT,
  status TEXT NOT NULL,
  duration_ms INTEGER,
  created_at TEXT NOT NULL
);

CREATE TABLE agent_memory (
  id TEXT PRIMARY KEY,
  agent_name TEXT NOT NULL,
  key TEXT NOT NULL,
  value_json TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(agent_name, key)
);

CREATE TABLE terminal_sessions (
  id TEXT PRIMARY KEY,
  label TEXT,
  created_at TEXT NOT NULL,
  ended_at TEXT,
  exit_code INTEGER
);

CREATE TABLE terminal_output (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL REFERENCES terminal_sessions(id) ON DELETE CASCADE,
  data TEXT NOT NULL,
  timestamp TEXT NOT NULL
);

CREATE TABLE processes (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  cmd TEXT NOT NULL,
  args_json TEXT,
  env_json TEXT,
  cwd TEXT,
  port INTEGER,
  status TEXT NOT NULL,
  pid INTEGER,
  started_at TEXT,
  stopped_at TEXT
);

CREATE TABLE process_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  process_id TEXT NOT NULL REFERENCES processes(id) ON DELETE CASCADE,
  stream TEXT NOT NULL CHECK(stream IN ('stdout','stderr')),
  line TEXT NOT NULL,
  timestamp TEXT NOT NULL
);

CREATE TABLE pipelines (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  definition_json TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  created_by TEXT
);

CREATE TABLE modules (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  code TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  created_by TEXT
);

CREATE TABLE adapters (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  adapter_type TEXT NOT NULL,
  config_json TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE network_sessions (
  token TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  remote_ip TEXT,
  used INTEGER NOT NULL DEFAULT 0,
  revoked INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE telemetry (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_type TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  timestamp TEXT NOT NULL
);

CREATE TABLE app_config (
  key TEXT PRIMARY KEY,
  value_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

## V2 Migration — Immutable Telemetry

```sql
CREATE TRIGGER telemetry_immutable
BEFORE DELETE ON telemetry
BEGIN
  SELECT RAISE(ABORT, 'telemetry rows are immutable');
END;

CREATE TRIGGER telemetry_no_update
BEFORE UPDATE ON telemetry
BEGIN
  SELECT RAISE(ABORT, 'telemetry rows are immutable');
END;
```

## Notes

- WAL mode enabled: `PRAGMA journal_mode=WAL`
- `PRAGMA synchronous=NORMAL` for performance
- Telemetry rows can only be INSERTed, never DELETEd or UPDATEd
- All timestamps stored as ISO 8601 strings in TEXT columns
