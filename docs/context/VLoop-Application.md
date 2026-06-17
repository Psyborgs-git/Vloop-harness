# VLoop Application

## Overview
The core software system. VLoop is a local-first orchestration engine for autonomous agents, ensuring strict security and resource limits.

## Responsibilities
- Orchestrates complex tasks by compiling them into DAG workflows.
- Supervises agent execution in isolated sandboxes.
- Tracks and limits LLM API costs and token usage globally.

## Interactions
- **User**: Receives commands and presents HITL prompts.
- **Local Host OS**: Probes hardware for memory limits and persists state.
- **External LLM APIs**: Requests completions via LiteLLM.
- **Docker / Kubernetes**: Dispatches sandboxed workloads.
