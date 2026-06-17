# WorkflowManager

## Overview
State management for task DAGs.

## Responsibilities
- Creates workflows and records DAG nodes and their specific dependencies.
- Persists DAG state to the underlying `IRelationalDB` adapter (SQLite).

## Interactions
- **State Adapters**: Uses the database port to store workflow graphs.
