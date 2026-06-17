# Local Proxy

## Overview
A local FastAPI application acting as an OpenAI-compatible endpoint trap.

## Responsibilities
- Listens on `host.docker.internal:4000`.
- Intercepts LLM completion requests originating from isolated sandboxes (like the Aider harness).
- Strips fake API keys and routes the payload to the internal `LLMGateway`.

## Interactions
- **Execution Adapters (AiderAdapter)**: Sandboxes are configured to point to this proxy.
- **LLMGateway**: Forwards validated requests for token tracking.
