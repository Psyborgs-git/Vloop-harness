import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from harness.tools.db_tool import DatabaseTool
from harness.core.main_process import MainProcess
from harness.core.permissions import Permission
from harness.tools.exceptions import ConfirmationRequired

@pytest.fixture
def mock_mp():
    # Make sure we don't spec it strictly if properties are not available statically
    mp = MagicMock()
    mp.permissions.has.return_value = True
    mp.tools.confirmations.create.return_value = MagicMock(token="fake_token")
    return mp

@pytest.fixture
def db_tool(mock_mp):
    tool = DatabaseTool(mock_mp)
    # Mock _get_engine to return sqlite
    mock_engine = MagicMock()
    mock_engine.dialect.name = "sqlite"
    tool._get_engine = AsyncMock(return_value=mock_engine)
    return tool

@pytest.mark.asyncio
async def test_validate_sql_ast_read_only(db_tool):
    dialect = "sqlite"
    import sqlglot.expressions as exp

    # Valid simple select
    sql = "SELECT * FROM users"
    assert db_tool._validate_sql_ast(sql, dialect, (exp.Select,)) is None

    # Valid CTE select
    sql = "WITH cte AS (SELECT 1 AS a) SELECT * FROM cte"
    assert db_tool._validate_sql_ast(sql, dialect, (exp.Select,)) is None

    # Invalid read: contains multiple statements (chained injection)
    sql = "SELECT 1; DROP TABLE users"
    res = db_tool._validate_sql_ast(sql, dialect, (exp.Select,))
    assert res is not None
    assert res.success is False
    assert "Multiple statements" in res.error

    # Invalid read: mutation inside CTE
    sql = "WITH inserted AS (INSERT INTO users (name) VALUES ('test') RETURNING id) SELECT * FROM inserted"
    res = db_tool._validate_sql_ast(sql, dialect, (exp.Select,))
    assert res is not None
    assert res.success is False
    assert "Mutation statements" in res.error

    # Invalid read: not a select
    sql = "UPDATE users SET name = 'test'"
    res = db_tool._validate_sql_ast(sql, dialect, (exp.Select,))
    assert res is not None
    assert res.success is False
    assert "Operation only accepts SELECT" in res.error

@pytest.mark.asyncio
async def test_validate_sql_ast_write(db_tool):
    dialect = "sqlite"
    import sqlglot.expressions as exp
    allowed = (exp.Insert, exp.Update, exp.Delete)

    # Valid write
    sql = "INSERT INTO users (name) VALUES ('test')"
    assert db_tool._validate_sql_ast(sql, dialect, allowed) is None

    sql = "UPDATE users SET name = 'test2' WHERE id = 1"
    assert db_tool._validate_sql_ast(sql, dialect, allowed) is None

    sql = "DELETE FROM users WHERE id = 1"
    assert db_tool._validate_sql_ast(sql, dialect, allowed) is None

    # Invalid write: permanently blocked DDL
    sql = "DROP TABLE users"
    res = db_tool._validate_sql_ast(sql, dialect, allowed)
    assert res is not None
    assert res.success is False
    assert "DROP/TRUNCATE/ALTER" in res.error

    sql = "ALTER TABLE users ADD COLUMN age INT"
    res = db_tool._validate_sql_ast(sql, dialect, allowed)
    assert res is not None
    assert res.success is False
    assert "DROP/TRUNCATE/ALTER" in res.error

    # Invalid write: chained
    sql = "INSERT INTO users (name) VALUES ('test'); DROP TABLE users"
    res = db_tool._validate_sql_ast(sql, dialect, allowed)
    assert res is not None
    assert res.success is False
    assert "Multiple statements" in res.error

@pytest.mark.asyncio
async def test_validate_sql_ast_read_set_operations(db_tool):
    dialect = "sqlite"
    import sqlglot.expressions as exp

    # Valid UNION
    sql = "SELECT 1 UNION SELECT 2"
    assert db_tool._validate_sql_ast(sql, dialect, (exp.Select, exp.SetOperation)) is None

    # Valid INTERSECT
    sql = "SELECT 1 INTERSECT SELECT 2"
    assert db_tool._validate_sql_ast(sql, dialect, (exp.Select, exp.SetOperation)) is None
