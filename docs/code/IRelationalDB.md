# IRelationalDB

## Overview
The Hexagonal Port defining relational state storage.

## Responsibilities
- `connect() -> None`
- `execute_query(query, params) -> List[tuple]`
- `close() -> None`
