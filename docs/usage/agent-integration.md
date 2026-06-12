# Agent Integration

This guide explains how LLM Agents (like Hermes, OpenClaw, or Claude) should format their outputs to interact with the Sandbox.

## Tool Calling

Agents should use the `RemoteShell` tool. The Python orchestrator will translate these calls into gRPC commands.

### JSON Formatting

The LLM should emit JSON structured like this:

```json
{
  "action": "RemoteShell",
  "command": "npm install",
  "args": []
}
```

### Parsing Responses
Because of the `ContextCleaner` middleware, the agent will not see ANSI escape sequences or animation frames.
The output will look clean:

```
added 413 packages, and audited 414 packages in 5s
```

If an error trace is too large, the agent will see truncated output:
```
Error: Missing package.json
...[8,850 lines truncated]...
Failed at step 4.
```
The agent should be prompted to handle these `...[...]...` blocks gracefully and use `grep` or specific file reads to investigate further.
