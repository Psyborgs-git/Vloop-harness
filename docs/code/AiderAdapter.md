# AiderAdapter

## Overview
Inherits from `LocalDockerAdapter` to run the Aider coding harness.

## Responsibilities
- Provisions host workspace directories and initializes `git`.
- Mounts the workspace volume into the container.
- Injects environment variables (`OPENAI_API_BASE=http://host.docker.internal:4000/v1`) forcing Aider to use the VLoop Local Proxy.
