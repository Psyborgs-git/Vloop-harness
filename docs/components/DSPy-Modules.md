# DSPy Modules

## Overview
The intelligence layer containing `CodeGenerator` and `PolicyGenerator`.

## Responsibilities
- **CodeGenerator**: Takes an objective and feedback, returning raw Python code.
- **PolicyGenerator**: Analyzes generated code and outputs a strict JSON security policy (e.g., defining if network access or volume mounts are required).

## Interactions
- **AgentLoop**: Invoked during the compilation phase of a task.
