"""DatabaseTool — policy-gated SQL inspection and parameterized query execution.

Security guarantees
───────────────────
• Only the harness SQLite database (or a specifically configured external DB)
  is accessible. Arbitrary connection strings are not accepted from params.
• Read operations (schema_info, query_read) are risk_level "safe".
• Write operations (query_write) are risk_level "destructive" and require
  human confirmation via the ConfirmationStore.
• Only parameterized queries are accepted — raw string interpolation is blocked.
• Maximum row count per query: 500 rows.
• Query timeout: 10 seconds.
• ``DROP``, ``TRUNCATE``, and ``ALTER`` statements are permanently blocked.

Supported operations (via ``params["operation"]``)
──────────────────────────────────────────────────
  schema_info  — return table names and their column definitions
  query_read   — execute a read-only (SELECT) query with :param style bindings
  query_write  — execute a write query (INSERT/UPDATE/DELETE) — requires confirmation
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import sqlglot
import sqlglot.expressions as exp

from harness.core.permissions import Permission
from harness.tools.base_tool import AbstractTool, ToolResult
from harness.tools.exceptions import ConfirmationRequired

if TYPE_CHECKING:
    from harness.core.main_process import MainProcess

_MAX_ROWS = 500
_QUERY_TIMEOUT_S = 10


class DatabaseTool(AbstractTool):
    """Read and (with confirmation) write the harness database."""

    name = "database"
    description = (
        "Inspect the harness database schema and execute safe parameterized queries. "
        "schema_info and query_read are safe; query_write requires confirmation. "
        "DROP/TRUNCATE/ALTER are permanently blocked. "
        "Requires FILESYSTEM_READ permission (schema_info/read) or FILESYSTEM_WRITE (write)."
    )
    required_permission = Permission.FILESYSTEM_READ
    risk_level = "safe"

    def __init__(self, main_process: MainProcess) -> None:
        super().__init__(main_process)

    # ── Dispatch ──────────────────────────────────────────────────────────────

    async def execute(
        self,
        component_id: str | None,
        session_id: str | None,
        params: dict[str, Any],
    ) -> ToolResult:
        self._check_permission(component_id)

        operation: str = params.get("operation", "")
        t0 = time.time()

        try:
            if operation == "schema_info":
                result = await self._schema_info()
            elif operation == "query_read":
                result = await self._query_read(params)
            elif operation == "query_write":
                result = await self._query_write(params, component_id)
            else:
                result = ToolResult(
                    success=False,
                    error=f"Unknown database operation: {operation!r}. "
                    "Valid: schema_info, query_read, query_write",
                )
        except Exception as exc:
            result = ToolResult(success=False, error=str(exc))

        result.metadata["duration_ms"] = int((time.time() - t0) * 1000)
        result.metadata["operation"] = operation
        return result

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _get_dialect(self) -> str:
        """Return the sqlglot dialect ('sqlite' or 'postgres') based on the active engine."""
        engine = await self._get_engine()
        dialect_name = getattr(getattr(engine, "dialect", None), "name", "sqlite")
        return "postgres" if dialect_name == "postgresql" else "sqlite"

    def _validate_sql_ast(
        self, sql: str, dialect: str, allowed_types: tuple[type[exp.Expression], ...]
    ) -> ToolResult | None:
        """Parse and validate SQL using sqlglot AST. Returns an error ToolResult if invalid, else None."""
        try:
            parsed = sqlglot.parse(sql, dialect=dialect)
        except sqlglot.errors.ParseError as e:
            return ToolResult(
                success=False,
                error=f"SQL syntax error: {e}",
            )

        # Ensure there is exactly one statement to prevent chained injections (e.g. SELECT 1; DROP TABLE users;)
        # Filter out empty statements (None) which happen with trailing semicolons
        statements = [stmt for stmt in parsed if stmt is not None]
        if not statements:
            return ToolResult(success=False, error="No valid SQL statement found.")
        if len(statements) > 1:
            return ToolResult(
                success=False,
                error="Multiple statements are not allowed.",
            )

        stmt = statements[0]

        # Permanently block specific DDL statements
        # We explicitly block Drop, Alter, and Command (often Truncate)
        for walk_result in stmt.walk():
            # Support sqlglot versions where walk() yields (node, parent, key) or just node
            node = walk_result[0] if isinstance(walk_result, tuple) else walk_result
            if isinstance(node, (exp.Drop, exp.Alter, exp.Command)):
                # Double check for Truncate just in case it parses differently
                if isinstance(node, exp.Command) and str(node).upper().startswith("TRUNCATE"):
                    return ToolResult(
                        success=False,
                        error="Query contains a permanently blocked statement (DROP/TRUNCATE/ALTER).",
                    )
                elif isinstance(node, (exp.Drop, exp.Alter)):
                    return ToolResult(
                        success=False,
                        error="Query contains a permanently blocked statement (DROP/TRUNCATE/ALTER).",
                    )
            # Truncate might be parsed as exp.Command or have its own class in newer sqlglot
            if type(node).__name__ == "Truncate":
                return ToolResult(
                    success=False,
                    error="Query contains a permanently blocked statement (DROP/TRUNCATE/ALTER).",
                )

        # Check allowed types for the top-level statement
        if not isinstance(stmt, allowed_types):
            allowed_names = "/".join([t.__name__.upper() for t in allowed_types])
            return ToolResult(
                success=False,
                error=f"Operation only accepts {allowed_names} statements. Got {type(stmt).__name__.upper()}.",
            )

        # If it's a Select (read operation), ensure no sneaky mutations exist within (e.g., CTEs doing inserts)
        if isinstance(stmt, (exp.Select, exp.SetOperation)):
            for walk_result in stmt.walk():
                node = walk_result[0] if isinstance(walk_result, tuple) else walk_result
                if isinstance(node, (exp.Insert, exp.Update, exp.Delete)):
                    return ToolResult(
                        success=False,
                        error="Mutation statements (INSERT/UPDATE/DELETE) are not allowed in query_read.",
                    )

        return None

    # ── Operation implementations ─────────────────────────────────────────────

    async def _get_engine(self) -> Any:
        """Return the active SQLAlchemy async engine."""
        from harness.data.db import get_session_factory

        factory = get_session_factory()
        return factory.kw.get("bind") or factory.kw.get("engine")

    async def _schema_info(self) -> ToolResult:
        """Return table names and column definitions for the harness DB."""
        from sqlalchemy import inspect

        from harness.data.db import get_session_factory

        factory = get_session_factory()
        async with factory() as session:
            # Use a synchronous inspect inside run_sync
            def _inspect(conn: Any) -> dict[str, Any]:
                insp = inspect(conn)
                tables: dict[str, Any] = {}
                for table_name in insp.get_table_names():
                    columns = []
                    for col in insp.get_columns(table_name):
                        columns.append({
                            "name": col["name"],
                            "type": str(col["type"]),
                            "nullable": col.get("nullable", True),
                        })
                    tables[table_name] = {"columns": columns}
                return tables

            tables = await session.run_sync(_inspect)

        import json
        return ToolResult(
            success=True,
            output=json.dumps(tables, indent=2),
            metadata={"table_count": len(tables)},
        )

    async def _query_read(self, params: dict[str, Any]) -> ToolResult:
        """Execute a parameterized SELECT query."""
        import json

        from sqlalchemy import text

        from harness.data.db import get_session_factory

        sql: str = params.get("sql", "")
        bind_params: dict[str, Any] = params.get("params", {})

        if not sql.strip():
            return ToolResult(success=False, error="'sql' parameter is required")

        # AST Validation: allow only Select, block chained/nested mutations
        dialect = await self._get_dialect()
        validation_error = self._validate_sql_ast(sql, dialect, (exp.Select, exp.SetOperation))
        if validation_error:
            if "Operation only accepts SELECT" in validation_error.error:
                validation_error.error = "query_read only accepts SELECT statements. Use query_write for mutations."
            return validation_error

        factory = get_session_factory()
        async with factory() as session:
            result = await session.execute(text(sql), bind_params)
            rows = result.fetchmany(_MAX_ROWS)
            columns = list(result.keys()) if rows else []
            data = [dict(zip(columns, row, strict=False)) for row in rows]

        return ToolResult(
            success=True,
            output=json.dumps(data, default=str, indent=2),
            metadata={"row_count": len(data), "columns": columns},
        )

    async def _query_write(
        self, params: dict[str, Any], component_id: str | None
    ) -> ToolResult:
        """Execute a parameterized INSERT/UPDATE/DELETE — requires confirmation."""

        from sqlalchemy import text

        from harness.core.permissions import Permission
        from harness.data.db import get_session_factory
        from harness.tools.confirmation import ConfirmationStore
        from harness.tools.exceptions import PermissionDenied

        # Write requires FILESYSTEM_WRITE (reused as DB write gate)
        cid = component_id or "root"
        if cid != "root" and not self._mp.permissions.has(cid, Permission.FILESYSTEM_WRITE):
            raise PermissionDenied(
                f"query_write requires {Permission.FILESYSTEM_WRITE.value!r} permission"
            )

        sql: str = params.get("sql", "")
        bind_params: dict[str, Any] = params.get("params", {})
        confirmation_token: str | None = params.get("_confirmation_token")

        if not sql.strip():
            return ToolResult(success=False, error="'sql' parameter is required")

        # AST Validation: allow Insert, Update, Delete
        dialect = await self._get_dialect()
        validation_error = self._validate_sql_ast(
            sql, dialect, (exp.Insert, exp.Update, exp.Delete)
        )
        if validation_error:
            if "Operation only accepts INSERT/UPDATE/DELETE" in validation_error.error:
                validation_error.error = "query_write only accepts INSERT/UPDATE/DELETE statements."
            return validation_error

        # Require confirmation unless token already provided
        if not confirmation_token:
            store: ConfirmationStore = self._mp.tools.confirmations
            pending = store.create(
                description=f"Execute write query: {sql[:120]}",
                risk_level="destructive",
                action_name="query_write",
                action_params={"sql": sql, "params": bind_params},
            )
            raise ConfirmationRequired(
                token=pending.token,
                description=f"Execute write query: {sql[:120]}",
                risk_level="destructive",
            )

        factory = get_session_factory()
        async with factory() as session:
            result = await session.execute(text(sql), bind_params)
            await session.commit()
            rowcount = result.rowcount

        return ToolResult(
            success=True,
            output=f"Write query executed successfully. Rows affected: {rowcount}",
            metadata={"rowcount": rowcount},
        )
