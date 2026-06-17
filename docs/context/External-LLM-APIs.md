# External LLM APIs

## Overview
Third-party language model providers (e.g., OpenAI, Anthropic, AWS Bedrock).

## Responsibilities
- Provide LLM completions for DSPy-driven code generation, policy generation, and agent reasoning.

## Interactions
- **VLoop Application (Python CP)**: Receives HTTP/REST requests routed through the internal `LLMGateway` and LiteLLM router. VLoop dynamically injects API keys at runtime so they are never hardcoded.
