# Tool Runtime

VLoop Harness includes a safe tool runtime layer that allows AI components and
pipelines to execute terminal commands and file operations within strict
security boundaries.

---

## Architecture Overview

```
MainProcess
  └── tools: ToolRegistry
        ├── policy: PolicyEngine          (three-tier security model)
        ├── confirmations: ConfirmationStore  (short-lived action tokens)
        ├── terminal: TerminalTool        (safe subprocess execution)
        └── filesystem: FilesystemTool    (safe file/dir operations)
```

The `ToolRegistry` is initialised during `MainProcess.boot()` and wired into
the `PipelineBuilder` so that pipelines can include tool steps.

---

## Security Model

### Three-Tier Policy

Policy is evaluated in this order (highest priority first):

| Tier | Description | Overridable? |
|------|-------------|--------------|
| **Permanent blocklist** | Always blocked (builtins + project config). | No |
| **Denylist** | Blocked by default; removable by project admins. | Project policy only |
| **Allowlist** | Per-directory list of permitted commands. | Yes, per-directory |

Built-in permanent blocklist entries include: `mkfs`, `fdisk`, `parted`,
`shred`, `wipefs`.  These cannot be removed regardless of policy configuration.

### Policy Files

| Location | Purpose |
|----------|---------|
| `<workspace_root>/.vloop/policy.json` | Project-local policy (not committed) |
| `~/.vloop/policy.json` | Global policy (applies to all projects) |

Neither file is tracked by git (`.vloop/` is in `.gitignore`).

### Policy Schema

```json
{
  "permanent_blocklist": ["custom_dangerous_cmd"],
  "denylist": ["sudo", "su", "passwd"],
  "directories": [
    {
      "directory": ".",
      "allowed_commands": ["python", "pytest", "ruff"],
      "allowed_arg_patterns": {
        "python": ["-m \\w+"]
      },
      "max_runtime_seconds": 30,
      "max_output_bytes": 524288
    },
    {
      "directory": "scripts",
      "allowed_commands": ["bash", "sh"],
      "max_runtime_seconds": 60
    }
  ]
}
```

**Field reference:**

- `directory` — path relative to `workspace_root`. The most-specific matching
  directory wins. A command allowed in `./scripts` is **not** implicitly
  allowed in `.` unless declared there too.
- `allowed_commands` — base binary names (without path).
- `allowed_arg_patterns` — optional per-command regex list. If specified, the
  joined argument string must match at least one pattern.
- `max_runtime_seconds` — default 30. Hard-kills the process on timeout.
- `max_output_bytes` — default 512 KiB. Truncates stdout + stderr.

### Workspace Boundary

`workspace_root` is captured once at `harness run` startup as `os.getcwd()`
(the CWD when the CLI is invoked).  All paths are resolved (`Path.resolve()`)
and checked to be inside `workspace_root` before any I/O.  Symlinks are
resolved before the boundary check.

### Shell Injection Prevention

The `TerminalTool` never uses `shell=True`.  Before parsing, the command string
is scanned for injection patterns including `$()`, backticks, `${…}`, pipes,
redirects, `eval`, and semicolon chaining.  A match immediately rejects the
command.

### Environment Stripping

Every subprocess receives only: `PATH`, `HOME`, `LANG`, `TERM`, `USER`,
`LOGNAME`.  The parent process environment is **not** inherited.

---

## Destructive Action Confirmation

Operations classified as `caution` or `destructive` require human confirmation:

| Operation | Risk level |
|-----------|-----------|
| `write` (overwriting existing file) | caution |
| `create` (new file/dir) | safe |
| `delete` | destructive |
| `move` / `rename` | destructive |

**Flow:**

1. Tool raises `ConfirmationRequired` with a short-lived token (60 s TTL).
2. API route catches it and returns **HTTP 202** with the token and a
   human-readable description.
3. Frontend shows `ConfirmDialog` with Confirm / Cancel.
4. User clicks Confirm → `POST /api/tools/confirm/{token}` → action executes.
5. User clicks Cancel → `DELETE /api/tools/confirm/{token}` → action discarded.
6. If the token expires, the action is auto-discarded.

Tokens are stored in-memory only (never persisted to DB).

---

## Terminal Tool

**Required permission:** `SHELL_EXEC`

**Request:**
```json
{
  "command": "pytest -v tests/",
  "cwd_relative": ".",
  "timeout": 60
}
```

**Response:**
```json
{
  "success": true,
  "output": "...",
  "error": null,
  "exit_code": 0,
  "metadata": {
    "command": "pytest -v tests/",
    "cwd": "/path/to/workspace",
    "duration_ms": 1234,
    "truncated": false
  }
}
```

---

## Filesystem Tool

**Required permission:** `FILESYSTEM_READ` (read ops) / `FILESYSTEM_WRITE` (write ops)

### Operations

| Operation | Risk | Params |
|-----------|------|--------|
| `list` | safe | `path` |
| `read` | safe | `path` |
| `stat` | safe | `path` |
| `write` | caution (if overwriting) | `path`, `content`, `create_parents?` |
| `create` | caution | `path`, `is_dir?` |
| `delete` | destructive | `path`, `recursive?` |
| `move` | destructive | `src`, `dest` |

---

## API Reference

See [`api-reference.md`](api-reference.md) for the full `/api/tools/*` endpoint
documentation.

---

## Using Tools from Components

```python
class MyComponent(BaseComponent):
    default_permissions = {Permission.SHELL_EXEC}

    async def on_mount(self) -> None:
        result = await self.run_tool("terminal", command="pytest", cwd_relative=".")
        if result.success:
            await self.update_state({"test_output": result.output})
```

`run_tool` enforces the component's permissions and the current policy before
executing.

---

## Pipeline Tool Steps

Pipelines support mixed component + tool steps:

```json
{
  "name": "Test and summarise",
  "steps": [
    {
      "type": "tool",
      "tool_name": "terminal",
      "config": {
        "command": "pytest -v {test_path}",
        "cwd_relative": ".",
        "timeout": 120,
        "input_map": {"test_path": "test_path"}
      }
    },
    {
      "type": "component",
      "component_id": "comp_summariser",
      "config": {
        "input_map": {"text": "output"}
      }
    }
  ]
}
```

Destructive tool steps pause the pipeline and emit a `requires_confirmation`
event.  The pipeline resumes only after the user confirms via the Tools panel
or the chat UI.

---

## React UI

The **Tools** tab (accessible from the left sidebar) contains:

- **Terminal** — command input, output area, history, CWD display.
- **Filesystem** — tree navigator, file viewer, create/delete/rename with
  confirmation dialogs.
- **Policy** — view and edit the project-local policy JSON.

All destructive actions surface `ConfirmDialog` before execution.
