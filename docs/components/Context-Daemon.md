# Context Daemon

## Overview
Rust daemon managing active LLM context.

## Responsibilities
- Maintains the current working context, system prompts, and global state required by the UI or Swarm processes.

## Interactions
- **Tauri UI**: Syncs context state for visual display.
