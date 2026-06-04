import asyncio
import time
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from sqlalchemy import inspect

async def setup_db():
    engine = create_async_engine('postgresql+asyncpg://postgres:postgres@localhost/postgres', echo=False)
    async_session = sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )

    try:
        async with engine.begin() as conn:
            # Clean up first
            await conn.execute(text("DROP SCHEMA IF EXISTS test_schema CASCADE"))
            await conn.execute(text("CREATE SCHEMA test_schema"))

            for i in range(10):
                await conn.execute(text(f"CREATE TABLE test_schema.table_{i} (id SERIAL PRIMARY KEY, name TEXT, value REAL, is_active BOOLEAN)"))
    except Exception as e:
        print(f"Failed to setup Postgres DB, skipping PG test: {e}")
        return None, None

    return engine, async_session

async def method8(session):
    def _inspect(conn):
        insp = inspect(conn)
        tables = {}

        if hasattr(insp, "get_multi_columns"):
            multi_cols = insp.get_multi_columns(schema="test_schema")
            print("multi_cols keys (PG):", multi_cols.keys())

        return tables

    return await session.run_sync(lambda session: _inspect(session.connection()))

async def main():
    engine, session_factory = await setup_db()
    if engine is None: return

    async with session_factory() as session:
        await method8(session)

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
