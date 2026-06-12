# Network Whitelisting

The Rust kernel translates user-defined domain whitelists into isolated network rules.

## The Proxy Mechanism

1. **Docker Isolation:** Sandboxes are launched with `--network none`.
2. **Internal Proxy:** The Rust Kernel runs a lightweight HTTP/HTTPS proxy on a dedicated bridge network.
3. **Routing:** The Docker container is linked to this bridge, and its `HTTP_PROXY` and `HTTPS_PROXY` environment variables are injected.
4. **Enforcement:** When the container attempts to resolve `registry.npmjs.org`, the Rust proxy checks the SQLite whitelist. If allowed, it forwards the traffic. If denied, it drops the connection instantly.
