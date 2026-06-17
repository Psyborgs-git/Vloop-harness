# LLMGateway

## Overview
The central Cost and Token Gateway wrapping LiteLLM.

## Responsibilities
- Tracks global token usage for the session.
- Enforces hard token cutoffs; raises `TokenLimitExceeded` if breached.
- Implements `SemanticCacheInterceptor` to bypass redundant LLM calls using the `IVectorStore`.

## Interactions
- **Local Proxy**: Receives intercepted sandbox requests.
- **External LLMs**: Makes the actual authenticated calls using real API keys.
