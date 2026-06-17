# Tauri UI

## Overview
The frontend interface built with React, Vite, and TypeScript.

## Responsibilities
- Provides the visual dashboard for workflow DAGs, logs, and token usage.
- Implements the secure credential Vault (using OS-native credential managers) to hold API keys.
- Renders HITL (Human-in-the-Loop) interception prompts.

## Interactions
- **Rust Microkernel**: Sends initialization commands, configuration updates, and temporary runtime API keys via Tauri IPC.
