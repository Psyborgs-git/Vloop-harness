# Security Model

## Threat Model
The Python Cognitive Engine is treated as an **untrusted guest**. Since it executes dynamic LLM outputs, it is highly susceptible to prompt injection and rogue tool execution.

## Boundaries
* **Application Boundary:** The Python engine cannot access the host OS directly for critical tasks; it must request them via the Rust Kernel.
* **Network Boundary:** Docker sandboxes are provisioned with `--network none`. An HTTP/HTTPS proxy inside the Rust Kernel enforces domain whitelisting.

## Capabilities
* **Python Engine CAN:**
  - Request a sandbox provision.
  - Send raw text or control keys to `stdin`.
  - Terminate a session.
* **Python Engine CANNOT:**
  - Modify the SQLite whitelist or policy configuration.
  - Bypass the `--network none` proxy constraint.
  - Access raw, unstripped logs without requesting them through the kernel.
