# ADR 003: ANSI Stripping & Context Cleaning Middleware

## Status
Accepted

## Context
LLMs fail catastrophically and waste massive amounts of tokens when fed raw TTY outputs containing ANSI color codes and carriage-return-based (`\r`) loading animations.

## Decision
Implemented a pure Python middleware (`ContextCleaner`) that acts before terminal data enters the LLM's memory window. It aggressively strips ANSI escape sequences, squashes carriage returns to show only the final state of loading bars, and truncates massive stack traces (keeping only the top and bottom).

## Consequences
- **Pros:** Dramatically reduces token usage and improves LLM reasoning by providing a clean, settled view of the terminal.
- **Cons:** Loss of terminal formatting fidelity in the LLM's context. Requires heuristics to avoid accidentally removing meaningful text.
